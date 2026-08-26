import cv2
import numpy as np
import requests
import base64
import json
import re
import time
import logging
import threading
from pathlib import Path
from typing import Optional, Dict, Any

log = logging.getLogger(__name__)

# Debug: VLM'e gönderilen kolajı diske kaydet.
# ÖNEMLİ: Bu yol config.py'deki DEBUG_VLM_DIR ile birebir aynı olmalı.
try:
    from src.config import DEBUG_VLM_DIR
except ImportError:
    DEBUG_VLM_DIR = Path(__file__).parent / "pipeline_output" / "debug_vlm"
DEBUG_VLM_DIR.mkdir(parents=True, exist_ok=True)

# Model/adres/zamanlama config.py'den okunur; config.py yoksa önceki sabit varsayılanlara düşer.
try:
    from src.config import (
        VLM_MODEL_NAME, VLM_API_URL, VLM_API_KEY, VLM_ENGINE_MIN_CALL_INTERVAL_S,
        VLM_VOTE_WINDOW, VLM_NUM_PREDICT, VLM_TIMEOUT_S, VRAG_ENABLED,
        VLM_DEBUG_SAVE_IMAGES
    )
except ImportError:
    VLM_MODEL_NAME = "llm-fast"
    VLM_API_URL = "https://evren-llmapi.ssyz.org.tr/v1/chat/completions"
    VLM_API_KEY = ""
    VLM_ENGINE_MIN_CALL_INTERVAL_S = 3.0
    VLM_VOTE_WINDOW = 5
    VLM_NUM_PREDICT = 2048
    VLM_TIMEOUT_S = 120.0
    VLM_DEBUG_SAVE_IMAGES = False

# Kolaj parametreleri
try:
    from src.config import COLLAGE_CELL_SIZE, COLLAGE_BORDER_PX, COLLAGE_BG_COLOR
except ImportError:
    COLLAGE_CELL_SIZE = 384
    COLLAGE_BORDER_PX = 3
    COLLAGE_BG_COLOR  = (30, 30, 30)

from .prompts import CROSS_CHECK_KEYWORDS, generate_vlm_prompt


def _build_vrag_context(matches: list) -> str:
    """VRAG eşleşmelerinden VLM'e verilecek bağlam metnini oluşturur.

    BUG-FIX (körü körüne güven): Eskiden burada "%80 üzeriyse BU KESİN BİR
    EŞLEŞMEDİR, DOĞRUDAN kullan" talimatı vardı — VLM'in VRAG yanlış olsa bile
    onu papağan gibi tekrarlamasına yol açıyordu (F-16-hep-çıkma hatası).
    Artık kesin/körü körüne güven kararı KOD seviyesinde, deterministik olarak
    veriliyor (pipeline.py: VRAG_GUVEN_ESIGI, >=%90 iken VRAG'ın cevabı zaten
    doğrudan nihai sonuca yazılıyor — prompt'un bunu ayrıca zorlamasına gerek
    yok). Bu metnin görevi SADECE %90 altındaki durumda VLM'e VRAG'ı bir DESTEK/
    ipucu olarak sunmak — VLM kendi gözlemine dayanarak nihai kararı kendisi
    verir, VRAG'ı görmezden gelmez ama ona da dikte edilmiş gibi davranmaz.
    """
    if not matches:
        return ""
    lines = [
        "GÖRSEL HAFIZA (VRAG) EŞLEŞMELERİ:",
        "Veritabanımızdaki bilinen hedeflerle yapılan vektörel karşılaştırma sonuçları "
        "(bir ipucu/destektir, kesin doğru olmak zorunda değil):",
    ]
    for i, m in enumerate(matches, 1):
        belirsiz_etiketi = " [belirsiz eşleşme]" if m.get("dusuk_guven") else ""
        lines.append(
            f"- {i}. Model: {m['model']} (Sınıf: {m['class']}, Ülke: {m.get('ulke', 'Bilinmiyor')}, "
            f"Benzerlik: %{int(m['score']*100)}){belirsiz_etiketi}"
        )
    lines.append(
        "DEĞERLENDİRME REHBERİ: Bu eşleşmeleri kendi görsel analizini destekleyecek bir "
        "ipucu olarak kullan. Gördüğün silüet/şekil bunlarla uyuşuyorsa ve '[belirsiz "
        "eşleşme]' işareti yoksa, VRAG'ın verdiği Model/Ülke bilgisini değerlendirmene "
        "dahil edebilirsin. Ama gördüğün görsel VRAG'ın dediğinden belirgin şekilde "
        "farklıysa ya da eşleşme '[belirsiz eşleşme]' işaretliyse, VRAG'a KÖRÜ KÖRÜNE "
        "GÜVENME — kendi gözlemine dayanarak NİHAİ KARARI SEN VER; gerekirse "
        "'hedef_modeli': 'Bilinmiyor' de. Yüksek benzerlikli, çok güvenilir eşleşmeler "
        "zaten ayrıca değerlendirilip gerektiğinde nihai sonuca otomatik yansıtılıyor — "
        "senin görevin burada kendi bağımsız gözlemini vermek."
    )
    return "\n".join(lines) + "\n"


class VLMEngine:
    def __init__(self, model_name: str = VLM_MODEL_NAME, api_url: str = VLM_API_URL,
                 min_recall_interval_s: float = VLM_ENGINE_MIN_CALL_INTERVAL_S, vote_window: int = VLM_VOTE_WINDOW,
                 api_key: str = VLM_API_KEY):
        self.model_name = model_name
        self.api_url = api_url
        self.api_key = api_key

        # --- Aynı track_id için gereksiz tekrar çağrı koruması ---
        # NEDEN: pipeline.py'de VLM'in track başına tek sefer çalışması
        # bekleniyor (`track.vlm_done`), ama okluzyon sonrası tracker
        # aynı ID ile yeni bir Track nesnesi oluşturursa bu kilit sıfırlanıyor
        # ve aynı ID defalarca (loglarda 55 kez!) VLM'e gönderiliyor.
        # Kaynak pipeline/tracker tarafında düzelmese bile, motor burada
        # kendini korur: aynı track_id için min_recall_interval_s dolmadan
        # gerçek bir API çağrısı yapmaz, bunun yerine son (oylanmış) sonucu
        # döndürür. Ollama/GPU'yu spam'den korur.
        self.min_recall_interval_s = min_recall_interval_s
        self._last_call_time: Dict[int, float] = {}
        self._last_result: Dict[int, Dict[str, Any]] = {}
        self._lock = threading.Lock()
        # BUG-FIX (VLM spam yarış durumu): Lock HTTP isteği sırasında serbest
        # bırakılıyor. _last_result'a eklenmemiş bir track_id için aynı anda
        # birden fazla thread API çağrısı yapabiliyordu. Artık aktif olarak
        # işlenen track'ler bu set ile izleniyor.
        self._in_flight_tracks: set[int] = set()

        # --- Zamansal çoğunluk oylaması ---
        # Aynı track_id birden çok kez analiz edilirse (istemli ya da
        # yukarıdaki bug yüzünden), tek karenin flip-flop'u yerine son
        # `vote_window` sonucun çoğunluk oyunu döndürür.
        self.aggregator = TrackVoteAggregator(window=vote_window)
        
        self.vrag_engine = None
        if VRAG_ENABLED:
            try:
                from src.vrag.engine import VRAGEngine
                self.vrag_engine = VRAGEngine()
            except Exception as e:
                log.error(f"[VRAG] Başlatılamadı: {e}")

    # ------------------------------------------------------------------
    # 1. GÖRSEL KOLAJ OLUŞTURMA
    # ------------------------------------------------------------------
    def _label_debug_image(self, img: np.ndarray, track_id: int, yolo_class: str,
                            yolo_conf: float, speed: float, threat: float) -> np.ndarray:
        """
        Diske kaydedilecek debug fotoğrafının üstüne (VLM'e giden orijinali
        DEĞİL, yalnızca kopyasına) okunaklı bir bilgi şeridi çizer:
        Track ID, YOLO sınıfı/güveni, hız ve tehdit skoru.
        """
        out = img.copy()
        h, w = out.shape[:2]

        label = f"ID:{track_id} | {yolo_class} %{int(yolo_conf*100)} | spd:{speed:.0f}px/s | thr:{threat:.2f}"
        font = cv2.FONT_HERSHEY_SIMPLEX
        scale = max(0.5, min(0.8, w / 700.0))
        thick = 2
        (lw, lh), _ = cv2.getTextSize(label, font, scale, thick)

        bar_h = lh + 16
        cv2.rectangle(out, (0, 0), (w, bar_h), (0, 0, 0), -1)
        cv2.putText(out, label, (8, bar_h - 10), font, scale, (0, 255, 0), thick, cv2.LINE_AA)

        ts_label = time.strftime("%Y-%m-%d %H:%M:%S")
        cv2.putText(out, ts_label, (8, h - 8), font, 0.45, (0, 255, 255), 1, cv2.LINE_AA)

        return out

    def build_visual_grid(self, crops: list[np.ndarray]) -> np.ndarray:
        """
        4 en iyi keyframe'i tek bir 768×768 kolaj görüntüsünde birleştirir.
        VLM'e tek görüntü olarak gönderilir.

        Layout:
          - 1 crop  → tek 768×768 (max netlik)
          - 2 crop  → yan yana 768×384
          - 3 crop  → üste 1 büyük (512×512) + alta 2 küçük (256×256) yan yana
          - 4 crop  → 2×2 grid (her hücre 384×384)

        İyileştirmeler (eskiden):
          - Siyah dolgu (np.zeros) → koyu gri COLLAGE_BG_COLOR zemin
          - Hücreler arası COLLAGE_BORDER_PX px gri border (VLM'e "bunlar ayrı anlar" mesajı)
          - 3-crop için boş 4. hücre yerine akıllı layout
          - INTER_LANCZOS4 → INTER_CUBIC (Lanczos4 keskin yapay kenarlar üretiyordu)
        """
        CELL    = COLLAGE_CELL_SIZE   # 384
        BORDER  = COLLAGE_BORDER_PX   # 3
        BG      = COLLAGE_BG_COLOR    # (30, 30, 30)

        valid_crops = [c for c in crops if c is not None and c.size > 0]
        if not valid_crops:
            return np.full((768, 768, 3), BG, dtype=np.uint8)

        def _prep(img: np.ndarray, cell_w: int, cell_h: int) -> np.ndarray:
            """
            crop'u belirtilen hücre boyutuna sığdır.
            - Aspect-ratio korunur
            - Kenar bantı: siyah değil koyu gri (BG rengi)
            - INTER_CUBIC: Lanczos4 yerine (yapay keskin kenar üretmez)
            """
            ih, iw = img.shape[:2]
            scale = min(cell_w / max(iw, 1), cell_h / max(ih, 1))
            nw = max(1, int(iw * scale))
            nh = max(1, int(ih * scale))
            resized = cv2.resize(img, (nw, nh), interpolation=cv2.INTER_CUBIC)
            canvas = np.full((cell_h, cell_w, 3), BG, dtype=np.uint8)
            x_off = (cell_w - nw) // 2
            y_off = (cell_h - nh) // 2
            canvas[y_off:y_off + nh, x_off:x_off + nw] = resized
            return canvas

        def _add_border_h(left: np.ndarray, right: np.ndarray) -> np.ndarray:
            """Yan yana iki pane arasına dikey border çizgisi ekle."""
            sep = np.full((left.shape[0], BORDER, 3), (60, 60, 60), dtype=np.uint8)
            return np.hstack((left, sep, right))

        def _add_border_v(top: np.ndarray, bottom: np.ndarray) -> np.ndarray:
            """Alt alta iki satır arasına yatay border çizgisi ekle."""
            sep = np.full((BORDER, top.shape[1], 3), (60, 60, 60), dtype=np.uint8)
            return np.vstack((top, sep, bottom))

        n = len(valid_crops)

        if n == 1:
            # Tek crop → 768×768 tam ekran (en yüksek çözünürlük)
            return _prep(valid_crops[0], 768, 768)

        elif n == 2:
            # Yan yana 2 pane, arasında border
            left  = _prep(valid_crops[0], CELL, CELL)
            right = _prep(valid_crops[1], CELL, CELL)
            return _add_border_h(left, right)

        elif n == 3:
            # Layout: üste büyük tek kare, alta iki küçük yan yana
            # Alt sıra genişliği: CELL * 2 + BORDER (384 + 3 + 384 = 771)
            bot_l   = _prep(valid_crops[1], CELL, CELL)
            bot_r   = _prep(valid_crops[2], CELL, CELL)
            bottom  = _add_border_h(bot_l, bot_r)
            top     = _prep(valid_crops[0], bottom.shape[1], CELL) # Genişliği alt sıra ile (771) bire bir eşleştir
            return _add_border_v(top, bottom)

        else:  # n == 4
            # 2×2 grid: hücreler arası border ile net ayırım
            tl = _prep(valid_crops[0], CELL, CELL)
            tr = _prep(valid_crops[1], CELL, CELL)
            bl = _prep(valid_crops[2], CELL, CELL)
            br = _prep(valid_crops[3], CELL, CELL)
            top_row    = _add_border_h(tl, tr)
            bottom_row = _add_border_h(bl, br)
            return _add_border_v(top_row, bottom_row)

    # ------------------------------------------------------------------
    # 3. ANALİZ FONKSİYONU
    # ------------------------------------------------------------------
    def analyze_target(self, track_id: int, crops: list[np.ndarray],
                       speed: float, zigzag: float, threat: float,
                       yolo_class: str, yolo_conf: float, vrag_matches: list = None) -> Optional[Dict[str, Any]]:

        # --- SPAM KORUMASI ---
        # pipeline.py "track başına tek sefer" VLM çağrısı bekler
        # (track.vlm_done), ama tracker.py'de okluzyon sonrası aynı
        # track_id'ye yeni bir Track nesnesi atanırsa bu kilit sıfırlanır
        # ve aynı ID kısa aralıklarla defalarca buraya düşebilir
        # (gerçek loglarda: Track ID 1 tek oturumda 55 kez, ~6sn arayla).
        # Motor bunu burada engeller: cooldown dolmadan gelen çağrılarda
        # gerçek bir API isteği ATMAZ, son (oylanmış) sonucu döndürür.
        with self._lock:
            last_call = self._last_call_time.get(track_id, 0.0)
            now = time.time()
            if (now - last_call) < self.min_recall_interval_s and track_id in self._last_result:
                log.info(f"[VLM] Track {track_id}: cooldown içinde ({now - last_call:.1f}s < "
                         f"{self.min_recall_interval_s}s) → API'ye gitmeden son sonuç döndürüldü.")
                return self._last_result[track_id]
            # BUG-FIX: Aynı track_id için zaten bir HTTP isteği uçuştaysa,
            # ikinci bir thread aynı anda Ollama'yı spamlemesin.
            if track_id in self._in_flight_tracks:
                log.debug(f"[VLM] Track {track_id}: zaten uçuşta (in-flight), atlandi.")
                return "IN_FLIGHT"
            self._in_flight_tracks.add(track_id)
            self._last_call_time[track_id] = now

        grid_img = self.build_visual_grid(crops)

        # --- Kolaj'ı diske kaydet (yalnızca VLM_DEBUG_SAVE_IMAGES=True iken) ---
        # Kaydedilen dosyayı src/vlm/manual_test.py ile açıp test edebilirsin:
        #   python -m src.vlm.manual_test pipeline_output/debug_vlm/track_X_....jpg
        #
        # BUG-FIX (FPS düşüşü): Bu blok eskiden HER VLM çağrısında koşulsuz
        # çalışıyordu — cv2.imwrite + etiket çizimi senkron CPU/disk işi, arka
        # plan thread'inde olsa bile Python'ın GIL'i yüzünden ana video işleme
        # döngüsüyle çekişip VLM tetiklendiği an FPS'in ani düşmesine yol
        # açıyordu. Artık yalnızca manuel debug için açıkça istendiğinde
        # (config.py: VLM_DEBUG_SAVE_IMAGES=True) çalışıyor.
        #
        # BUG-FIX (etiketsiz fotoğraf): Bu görsel doğrudan ham crop'tan
        # oluşuyordu — canlı videodaki HUD (ID/sınıf/güven kutusu) sadece
        # _draw_and_save() içindeki "vis" karesine çiziliyordu, buraya asla
        # ulaşmıyordu. Sonuç: diske kaydedilen HER track_X.jpg etiketsizdi.
        # VLM'e giden temiz görüntüyü (grid_img) BOZMADAN, sadece diske
        # yazılan kopyanın üstüne bilgi şeridi basıyoruz.
        if VLM_DEBUG_SAVE_IMAGES:
            try:
                DEBUG_VLM_DIR.mkdir(parents=True, exist_ok=True)
                fname = f"track_{track_id}_{int(time.time())}.jpg"
                save_path = DEBUG_VLM_DIR / fname

                labeled_img = self._label_debug_image(
                    grid_img, track_id=track_id, yolo_class=yolo_class, yolo_conf=yolo_conf,
                    speed=speed, threat=threat,
                )

                ok = cv2.imwrite(str(save_path), labeled_img)
                if ok:
                    log.info(f"[VLM-KOLAJ] Diske kaydedildi → {save_path}")
                else:
                    log.warning(f"[VLM-KOLAJ] imwrite başarısız → {save_path} (cv2 hata kodu)")
            except Exception as e:
                log.warning(f"[VLM-KOLAJ] Kayıt hatası: {e}")


        _, buffer = cv2.imencode('.jpg', grid_img, [int(cv2.IMWRITE_JPEG_QUALITY), 80])
        img_b64 = base64.b64encode(buffer).decode('utf-8')

        # VRAG Sorgusu (Eğer aktifse en iyi kırpılmış görüntüyü veritabanında ara)
        vrag_context = ""
        if vrag_matches:
            matches = vrag_matches
            log.info(f"[VRAG] ⚡ Mevcut Eşleşmeler Kullanıldı: " +
                     ", ".join([f"{m['model']} (%{int(m['score']*100)})" for m in matches]))
            vrag_context = _build_vrag_context(matches)
        elif self.vrag_engine and crops:
            matches = self.vrag_engine.search_similar_vehicle(crops[0])
            if matches:
                log.info(f"[VRAG] ⚡ Yeni Eşleşme Bulundu: " +
                         ", ".join([f"{m['model']} (%{int(m['score']*100)})" for m in matches]))
                vrag_context = _build_vrag_context(matches)

        prompt = generate_vlm_prompt(speed, zigzag, threat, yolo_class, yolo_conf, n_crops=len(crops), vrag_context=vrag_context)

        # OpenAI-uyumlu /v1/chat/completions (EVREN) — görsel içerik "image_url"
        # (data URI) parçası olarak content listesine eklenir.
        call_url = self.api_url
        payload = {
            "model": self.model_name,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{img_b64}"}},
                    ],
                }
            ],
            "temperature": 0.0,
            "top_p": 0.9,
            "max_tokens": VLM_NUM_PREDICT,
            "response_format": {"type": "json_object"},
        }
        headers = {"Authorization": f"Bearer {self.api_key}"} if self.api_key else None

        try:
            response = requests.post(call_url, json=payload, headers=headers, timeout=VLM_TIMEOUT_S)
            response.raise_for_status()

            resp_json = response.json()

            choices = resp_json.get("choices") or []
            # BUG-FIX: .get("content", "") sadece key hic yoksa "" doner; EVREN
            # bazen key'i "content": null olarak gonderiyor (ornegin model
            # gorsel girdiyi desteklemiyorsa) - bu durumda None doner ve
            # .strip() cokerdi, gercek hatayi (asagidaki log) hic gormeden.
            raw_text = (choices[0].get("message", {}).get("content") or "").strip() if choices else ""

            if not raw_text:
                log.warning(f"[VLM] Sunucu bos yanit dondu veya format taninmadi! Full API Cevabi: {resp_json}")

            # --- GÜÇLÜ JSON AYRISTIRMA ---
            # Gemma4 gibi "thinking" modelleri <think>...</think> blokları üretebilir. 
            # Önce bu blokları temizle.
            raw_text = re.sub(r'<think>.*?</think>', '', raw_text, flags=re.DOTALL).strip()
            
            start_idx = raw_text.find('{')
            end_idx = raw_text.rfind('}')
            
            clean = raw_text
            
            if start_idx != -1:
                if end_idx == -1 or end_idx < start_idx:
                    log.warning(f"[VLM] Yarım kalmış JSON tespit edildi, onarılmaya çalışılıyor...")
                    clean = raw_text[start_idx:]
                    if clean.count('"') % 2 != 0:
                        clean += '"'
                    clean += "}"
                else:
                    clean = raw_text[start_idx:end_idx+1]
                
                clean = re.sub(r'//[^\n]*', '', clean)
                
            try:
                if start_idx != -1:
                    result = json.loads(clean)
                else:
                    raise json.JSONDecodeError("No JSON block found", raw_text, 0)
            except json.JSONDecodeError:
                log.warning("[VLM] json.loads başarısız veya JSON bloğu yok, Regex ile veriler kurtarılıyor...")
                print(f"[VLM-DEBUG] Raw minicpm-v output:\n{raw_text}\n-------------------")
                result = {}
                keys = ["gorsel_analiz", "arac_sinifi", "tehdit_seviyesi", "tahmini_hedef_tipi"]
                for k in keys:
                    m = re.search(r'["\']?' + k + r'["\']?\s*:\s*["\']?([^"\',\n\}]*)', raw_text)
                    if m:
                        result[k] = m.group(1).strip()

            # --- SONUÇ DOĞRULAMA (Validation) ---
            valid_sınıf    = {"sabit_kanat", "doner_kanat", "kus", "bilinmeyen"}
            valid_tehdit   = {"yuksek", "orta", "dusuk", "yok"}
            valid_tip      = {"kamikaze", "siha", "iha", "askeri_ucak", "yolcu_ucagi",
                                "gozetleme", "ticari_drone", "dogal_yasam", "tanimsiz"}

            arac_sinifi_raw = str(result.get("arac_sinifi", "bilinmeyen")).strip().lower()
            # Eşanlamlı eşleştirmeler
            if "uçak" in arac_sinifi_raw or "ucak" in arac_sinifi_raw or "jet" in arac_sinifi_raw or "sabit" in arac_sinifi_raw:
                arac_sinifi_raw = "sabit_kanat"
            elif "helikopter" in arac_sinifi_raw or "drone" in arac_sinifi_raw or "doner" in arac_sinifi_raw or "döner" in arac_sinifi_raw:
                arac_sinifi_raw = "doner_kanat"
                
            result["arac_sinifi"] = arac_sinifi_raw
            result["tehdit_seviyesi"] = str(result.get("tehdit_seviyesi", "dusuk")).strip().lower()
            
            tip_raw = str(result.get("tahmini_hedef_tipi", "tanimsiz")).strip().lower()
            if "savaş" in tip_raw or "savas" in tip_raw or "avcı" in tip_raw:
                tip_raw = "askeri_ucak"
            result["tahmini_hedef_tipi"] = tip_raw

            if result["arac_sinifi"] not in valid_sınıf:
                result["arac_sinifi"] = "bilinmeyen"
            if result["tehdit_seviyesi"] not in valid_tehdit:
                result["tehdit_seviyesi"] = "dusuk"
            if result["tahmini_hedef_tipi"] not in valid_tip:
                result["tahmini_hedef_tipi"] = "tanimsiz"

            if not result.get("gorsel_analiz") or len(str(result.get("gorsel_analiz", ""))) < 3:
                # Fallback: prompt İngilizce olduğunda model visual_analysis doldurur
                if result.get("visual_analysis") and len(str(result.get("visual_analysis", ""))) >= 3:
                    result["gorsel_analiz"] = result["visual_analysis"]
                else:
                    result["gorsel_analiz"] = "Görsel analiz tamamlanamadı"

            leaked_tokens = valid_sınıf | valid_tehdit | valid_tip
            for free_field in ("hedef_modeli", "ulke_orjini"):
                val = str(result.get(free_field, "")).strip().lower()
                if val in leaked_tokens or not val:
                    result[free_field] = "Bilinmiyor"

            # Çapraz kontrol: hem diğer sınıfın anahtar kelimeleri hem de
            # beyan edilen sınıfın anahtar kelimeleri metinde yoksa çelişki var.
            # Not: İngilizce prompt artık visual_analysis kullanıyor.
            gorsel_lower = str(result.get("gorsel_analiz", "") or result.get("visual_analysis", "")).lower()
            declared_class = result.get("arac_sinifi")
            conflict = False
            if declared_class in CROSS_CHECK_KEYWORDS:
                declared_kws = CROSS_CHECK_KEYWORDS[declared_class]
                # Eğer beyan edilen sınıfın HİÇBİR anahtar kelimesi metinde yoksa
                # VE diğer sınıfın anahtar kelimeleri varsa → gerçek çelişki
                has_declared = any(kw in gorsel_lower for kw in declared_kws)
                for other_class, keywords in CROSS_CHECK_KEYWORDS.items():
                    if other_class == declared_class:
                        continue
                    has_other = any(kw in gorsel_lower for kw in keywords)
                    if has_other and not has_declared:
                        conflict = True
                        break
            result["_celiski_var"] = conflict
            if conflict:
                log.warning(
                    f"[VLM] Track {track_id}: arac_sinifi='{declared_class}' ile gorsel_analiz "
                    f"metni çelişiyor → '{gorsel_lower[:120]}'. tahmini_hedef_tipi tanimsiz'e düşürüldü."
                )
                if result["tahmini_hedef_tipi"] not in ("tanimsiz", "dogal_yasam"):
                    result["tahmini_hedef_tipi"] = "tanimsiz"

            stable = self.aggregator.update(track_id, result)
            with self._lock:
                self._last_result[track_id] = stable
            return stable

        except requests.exceptions.Timeout:
            log.error(f"[VLM] Track {track_id}: EVREN yanıt vermedi ({VLM_TIMEOUT_S:.0f}s timeout)")
            return None
        except Exception as e:
            log.error(f"[VLM] Track {track_id}: API hatası → {e}")
            return None
        finally:
            # BUG-FIX: Sonuç ne olursa olsun (başarı/hata/timeout)
            # track'i in-flight setinden çıkar — yoksa sonsuza dek bloklanır.
            with self._lock:
                self._in_flight_tracks.discard(track_id)

    def forget_track(self, track_id: int) -> None:
        """
        Bir track kalıcı olarak öldüğünde (tracker.py onu _states'ten
        sildiğinde) pipeline.py isteğe bağlı olarak bunu çağırabilir.
        Aksi halde ByteTrack aynı sayısal ID'yi çok sonra farklı bir
        hedefe verirse, o yeni hedef eski hedefin oy geçmişiyle karışabilir.
        Çağrılmazsa da sistem çalışır (sadece cache biraz "bayat" kalır).
        """
        with self._lock:
            self._last_call_time.pop(track_id, None)
            self._last_result.pop(track_id, None)
            self._in_flight_tracks.discard(track_id)
        self.aggregator.reset(track_id)

    def reset_all(self) -> None:
        """
        BUG-FIX (eski videodan kalan sonuç): forget_track() tek bir track_id
        için temizlik yapıyordu, ama yeni bir video oturumu başlarken
        tracker.reset() ByteTrack'in ID sayacını da sıfırlıyor — yani yeni
        videodaki ilk hedef, eski videodaki aynı (küçük) track_id'yi
        (örn. 0) alabiliyordu. VLM önbelleği (_last_result, oylama geçmişi)
        temizlenmediği için o track_id'ye ait ESKİ cevap (örn. "Kaan", 2/2
        tutarlılık) hiç yeni analiz yapılmadan geri dönüyordu. Yeni oturum
        başlarken tracker.reset() ile BİRLİKTE bu da çağrılmalı.
        """
        with self._lock:
            self._last_call_time.clear()
            self._last_result.clear()
            self._in_flight_tracks.clear()
        self.aggregator._history.clear()


class TrackVoteAggregator:
    """
    Tek bir VLM çağrısı, o anki kare şanslı/şanssız diye tutarsız sonuç
    verebilir (bkz. aynı track için bir seferinde 'sabit_kanat', bir
    seferinde 'doner_kanat'). Bu sınıf, her track_id için son N analiz
    sonucunu biriktirip alan bazında ÇOĞUNLUK OYU (majority vote) ile
    stabilize edilmiş, "kararlı" bir sonuç döndürür.

    NOT: VLMEngine.analyze_target() artık bunu OTOMATİK kullanıyor
    (self.aggregator) — pipeline.py tarafında ayrıca bir şey yapmana
    gerek yok, dönen sonuç zaten stabilize edilmiş olacak. Sınıf yine de
    dışarıdan bağımsız kullanılabilsin diye ayrı bırakıldı.
    """

    # BUG-FIX (gecikmeli/eski model ismi): "hedef_modeli" eskiden burada
    # oylanıyordu — VRAG artık doğru/net bir modele geçse bile, penceredeki
    # eski (yanlış) oylar çoğunlukta kaldığı sürece ekran YANLIŞ model ismini
    # göstermeye devam ediyordu (örn. VRAG "Kaan" dese bile birkaç kare daha
    # "F-16" görünüyordu). "hedef_modeli" artık oylanmıyor — her zaman EN SON
    # analizin ham sonucu gösteriliyor (gecikme yok). Bunun yerine, ne kadar
    # "kararlı" olduğunu göstermek için ayrı bir tutarlılık bilgisi ekleniyor
    # (_hedef_modeli_tutarlilik = "X/Y") — gösterimi geciktirmeden.
    VOTED_FIELDS = ("arac_sinifi", "tehdit_seviyesi", "tahmini_hedef_tipi",
                     "ulke_orjini")

    def __init__(self, window: int = 5):
        self.window = window
        self._history: Dict[int, list] = {}

    def update(self, track_id: int, result: Dict[str, Any]) -> Dict[str, Any]:
        hist = self._history.setdefault(track_id, [])
        hist.append(result)
        if len(hist) > self.window:
            hist.pop(0)

        stable = dict(result)  # gorsel_analiz, hedef_modeli gibi alanlar en son sonuçtan kalır
        for field in self.VOTED_FIELDS:
            votes = [h.get(field) for h in hist if h.get(field)]
            if not votes:
                continue
            # "Bilinmiyor"/"tanimsiz" gibi boş cevapları oylamada düşük öncelikli tut:
            # eğer bilgili bir çoğunluk varsa onu tercih et, yoksa bilinmiyor'a düş.
            informative = [v for v in votes if v not in ("Bilinmiyor", "bilinmeyen", "tanimsiz", "yok", "Belirsiz")]
            pool = informative if informative else votes
            counts: Dict[str, int] = {}
            for v in pool:
                counts[v] = counts.get(v, 0) + 1
            stable[field] = max(counts, key=counts.get)

        # Gecikmesiz tutarlılık göstergesi: son N analizin kaçı, ŞU AN
        # gösterilen (en güncel) hedef_modeli ile aynı fikirde.
        guncel_model = result.get("hedef_modeli")
        if guncel_model:
            ayni_fikirde = sum(1 for h in hist if h.get("hedef_modeli") == guncel_model)
            stable["_hedef_modeli_tutarlilik"] = f"{ayni_fikirde}/{len(hist)}"

        stable["_vote_count"] = len(hist)  # kaç analizden oylandığını göstermek için
        return stable

    def reset(self, track_id: int) -> None:
        """Track kaybolduğunda/yeniden ID atandığında geçmişi temizle."""
        self._history.pop(track_id, None)