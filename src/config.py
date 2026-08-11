# ============================================================
# config.py â€” Teknofest SavaÅŸan Ä°HA Pipeline Merkezi Kontrol Paneli
# ============================================================
# Modelin 3 sÄ±nÄ±fÄ±: 0=kite, 1=bird, 2=class_3 (drone/uav)
# Her parametre tek bir yerde tanÄ±mlanÄ±r.
# Gruplar: DonanÄ±m â†’ AlgÄ±lama â†’ Takip â†’ Filtreleme â†’ VLM â†’ Ã‡Ä±ktÄ±
# ============================================================
from pathlib import Path
import torch

# ======================== DONANIM ============================
DEVICE       = "cuda:0" if torch.cuda.is_available() else "cpu"
# VRAM tıkanıklığı (YOLO + VRAG + VLM/Ollama + LLM aynı GPU'da yarışıyordu) için
# VRAG (SigLIP2) kalıcı olarak CPU'ya alındı — GPU'da yalnızca YOLO ve Ollama kalsın.
VRAG_DEVICE  = "cpu"
MODEL_PATH   = str(Path(__file__).parent.parent / "models" / "best.pt")

# ======================== SAHI / SLICER ======================
# --- Pass-1: HÄ±zlÄ± Ã¶n tarama ---
PASS1_SIZE      = 640    # Frame bu boyuta kÃ¼Ã§Ã¼ltÃ¼lÃ¼r
PASS1_CONF      = 0.08   # Ã‡ok dÃ¼ÅŸÃ¼k: "bir ÅŸey var mÄ±?" kontrolÃ¼
PASS1_EXPAND_PX = 150    # ROI etrafÄ±na piksel geniÅŸletme

# --- Pass-2: YÃ¼ksek Ã§Ã¶zÃ¼nÃ¼rlÃ¼klÃ¼ SAHI tarama ---
SLICE_H    = 640         # PatÃ§a yÃ¼ksekliÄŸi
SLICE_W    = 640         # PatÃ§a geniÅŸliÄŸi
OVERLAP    = 0.25        # %25 Ã¶rtÃ¼ÅŸme (kenar nesnelerini koru)
NMS_IOU    = 0.20        # Ã‡akÄ±ÅŸan kutularÄ± agresif birleÅŸtirme eÅŸiÄŸi (0.30'dan 0.20'ye dÃ¼ÅŸÃ¼rÃ¼ldÃ¼)
BATCH_SIZE = 8           # GPU batch boyutu

# --- YOLO GÃ¼ven EÅŸikleri ---
CONFIDENCE          = 0.40   # YakÄ±n (bÃ¼yÃ¼k) hedefler iÃ§in minimum gÃ¼ven
FAR_TARGET_MIN_CONF = 0.15   # Uzak (kÃ¼Ã§Ã¼k) hedefler iÃ§in minimum gÃ¼ven (Teknofest iÃ§in dÃ¼ÅŸÃ¼k kalmalÄ± â€” Ã§ift eÅŸikli sistem gereksizleri eler)
FAR_TARGET_AREA_RATIO = 0.005  # Frame alanÄ±nÄ±n %0.5'inden kÃ¼Ã§Ã¼k = uzak hedef (0.002'den artÄ±rÄ±ldÄ±)

# --- Varyans Ã–n-Filtresi ---
# BoÅŸ gÃ¶kyÃ¼zÃ¼ patÃ§alarÄ±nÄ± YOLO'ya gÃ¶ndermeden eler.
# BUG-FIX (boÅŸluÄŸu Ä°HA sanma): 3.0 Ã§ok dÃ¼ÅŸÃ¼ktÃ¼ â€” hafif bulut/pus/kompresyon
# gÃ¼rÃ¼ltÃ¼sÃ¼ bile bu eÅŸiÄŸi geÃ§ip YOLO'ya gidiyor, dÃ¼ÅŸÃ¼k ama sÄ±fÄ±r olmayan
# bir gÃ¼venle "Ä°HA" tespiti Ã¼retebiliyordu. 5.0'a Ã§Ä±karÄ±ldÄ±: gerÃ§ek uzak
# hedeflerin kendi kontrastÄ± bunu rahatÃ§a geÃ§er, ama dÃ¼z/pÃ¼rÃ¼zsÃ¼z gÃ¶kyÃ¼zÃ¼
# patÃ§alarÄ± artÄ±k daha gÃ¼venilir ÅŸekilde elenir.
VARIANCE_THRESHOLD = 2.0     # BUG-FIX: 5.0 uzak/dÃ¼ÅŸÃ¼k kontrastlÄ± hedefleri siliyordu, 2.0 onlarÄ± yakalar, sahte pozitifler Ã§ift eÅŸikli gÃ¼ven filtresinde elenir

# --- Tam Frame Tarama DÃ¼ÅŸme KorumasÄ± ---
FULLSCAN_FALLBACK = True     # Pass-1 boÅŸ dÃ¶nerse tam tarama yap
FULLSCAN_STRIDE   = 640      # Tam frame grid tarama adÄ±mÄ± (px) â€” SLICE boyutuyla eÅŸleÅŸir, kÃ¼Ã§Ã¼k uzak hedef kenar kaÃ§Ä±rmayÄ± Ã¶nler
FULLSCAN_ALWAYS   = False     # [GÃœNCELLENDÄ°] True -> False: FPS'i inanÄ±lmaz dÃ¼ÅŸÃ¼rdÃ¼ÄŸÃ¼ (1000ms+) iÃ§in kapatÄ±ldÄ±. Sadece hedef kaybolduÄŸunda Fallback olarak Ã§alÄ±ÅŸacak!

# BUG-FIX (boÅŸluÄŸu uzun sÃ¼re Ä°HA sanma): FULLSCAN_ALWAYS=True olduÄŸunda
# HER karede, aktif olarak takip edilen gerÃ§ek bir hedef olsa bile, TÃœM
# frame zayÄ±f FAR_TARGET_MIN_CONF (0.25) ile taranÄ±yordu. Bu, arka plandaki
# dÃ¼ÅŸÃ¼k-ama-sÄ±fÄ±r-olmayan varyanslÄ± bÃ¶lgelerin (bulut kenarÄ±, gÃ¼neÅŸ
# yansÄ±masÄ±, sÄ±kÄ±ÅŸtÄ±rma bloÄŸu) sÃ¼rekli yeniden taranÄ±p yeni hayalet
# track'ler aÃ§masÄ±nÄ±n baÅŸlÄ±ca kaynaÄŸÄ±ydÄ±. ArtÄ±k: hiÃ§bir track yokken
# (ilk kilitlenme Ã¶ncesi, azami recall ÅŸart) her karede tam tarama
# sÃ¼rÃ¼yor; en az bir track (hint) varken tam tarama yalnÄ±zca her
# FULLSCAN_SKIP_FRAMES karede bir tekrarlanÄ±r â€” periyodik "baÅŸka yeni
# hedef var mÄ±?" kontrolÃ¼ olarak gÃ¶revini sÃ¼rdÃ¼rÃ¼r ama gÃ¼rÃ¼ltÃ¼ Ã¼retimini
# ciddi biÃ§imde azaltÄ±r.
FULLSCAN_SKIP_FRAMES = 30     # BUG-FIX: 4 -> 8 -> 30, periyodik lag spike'larÄ± azaltÄ±r, 30 karede bir yeni hedef tarama yeterli (~1s @30fps)

# --- Geometrik Filtreler ---
ROI_EXPAND           = 1.5   # ROI geniÅŸletme Ã§arpanÄ±
MIN_OBJECT_PX        = 3     # BUG-FIX: 8 â†’ 3 â€” UÃ§ak dikine daldÄ±ÄŸÄ±nda kalÄ±nlÄ±ÄŸÄ± (w) 3-4 piksele kadar dÃ¼ÅŸebiliyor
# BUG-FIX (yakÄ±n hedef tespiti reddediliyordu): 0.40 iken, hedef kameraya
# Ã§ok yaklaÅŸtÄ±ÄŸÄ±nda (tam da en kritik/en tehditkÃ¢r an!) kutu frame alanÄ±nÄ±n
# %40'Ä±nÄ± aÅŸÄ±yor ve is_valid_geometry() bu GERÃ‡EK ve EN Ã–NEMLÄ° tespiti
# reddedip track'i "kayÄ±p" durumuna dÃ¼ÅŸÃ¼rÃ¼yordu â€” box #1'in uÃ§aÄŸa
# yakÄ±nken 1-2sn "kaybolup" tekrar yapÄ±ÅŸmasÄ±nÄ±n olasÄ± nedenlerinden biri.
# 0.65'e Ã§Ä±karÄ±ldÄ±: aÅŸÄ±rÄ± yakÄ±n Ã§ekimlerde bile gerÃ§ek tespit artÄ±k kabul
# ediliyor; ekstrem durumlarda (kamera neredeyse tamamen uÃ§akla dolduÄŸunda)
# Nesne maksimum bÃ¼yÃ¼klÃ¼k oranÄ± (BÃ¼tÃ¼n bir ekranÄ±n %20'sinden bÃ¼yÃ¼kse uÃ§ak deÄŸil kokpit/yaprak sayÄ±lÄ±r)
MAX_OBJECT_AREA_RATIO = 0.95        # BUG-FIX: 0.65 â†’ 0.95 â€” ekstrem yakÄ±n (ekranÄ± kaplayan) uÃ§ak geÃ§iÅŸleri artÄ±k reddedilmeyecek
ASPECT_RATIO_MIN     = 0.10  # BUG-FIX: 0.25 â†’ 0.10 â€” mermi gibi diklemesine dalan Ä°HA'lar Ã§ok ince ve uzun olur (w/h = 0.10 olabilir)
ASPECT_RATIO_MAX     = 10.0  # BUG-FIX: 7.0 â†’ 10.0 â€” yatay uÃ§an ince kanat profilleri

# ======================== BYTETRACK / TAKÄ°P ==================
KALMAN_MAX_AGE       = 90    # Okluzyonda track yaÅŸatma (frame, ani manevra iÃ§in 1.5sn)
KALMAN_MIN_HITS      = 2     # Onay iÃ§in gereken minimum ardÄ±ÅŸÄ±k tespit
KALMAN_SUSPENDED_AGE = 75    # AskÄ±daki track Ã¶mrÃ¼ (frame, ani manevra korumasÄ±)
KALMAN_PROCESS_NOISE = 0.05
KALMAN_MEASURE_NOISE = 0.5

# ByteTrack parametreleri
BYTETRACK_MIN_CONF     = 0.15  # Tur-2 dÃ¼ÅŸÃ¼k gÃ¼ven eÅŸiÄŸi
BYTETRACK_TRACK_THRESH = 0.30  # Tur-1 yÃ¼ksek gÃ¼ven eÅŸiÄŸi
BYTETRACK_MATCH_THRESH = 0.80  # EÅŸleÅŸme IoU eÅŸiÄŸi

# --- SÄ±nÄ±f OylamasÄ± ---
# Modelde: 0=kite, 1=bird, 2=class_3 (drone/uav)
# Ekranda yalnÄ±zca class_3 (ID=2) gÃ¶sterilir.
#
# SORUN: Model bazÄ± kuÅŸlarÄ± class_3 (drone) olarak etiketliyor.
# Ã‡Ã–ZÃœM: Ã‡ok katmanlÄ± filtre:
#   1. CLASS_VOTE_MIN_CONF: YalnÄ±zca yÃ¼ksek gÃ¼venli oylar sayÄ±lÄ±r
#   2. CLASS_PRIORITY_THRESHOLD: Drone en az %50 oy almalÄ±
#   3. DISPLAY_MIN_CLASS_VOTE: Ekrana Ã§Ä±kmak iÃ§in %65 oy ÅŸartÄ±
#   4. DISPLAY_MIN_HITS: En az 10 frame gÃ¶rÃ¼len track onaylanÄ±r
CLASS_VOTE_MIN_CONF      = 0.25   # Oylama iÃ§in minimum YOLO gÃ¼veni
CLASS_VOTE_HISTORY       = 30     # Son kaÃ§ frame'in oyu sayÄ±lÄ±r
CLASS_PRIORITY_THRESHOLD = 0.50   # BUG-FIX: 0.35 â†’ 0.50 â€” birkaÃ§ yanlÄ±ÅŸ drone oyu kuÅŸu Ä°HA yapmasÄ±n, Ã§oÄŸunluk ÅŸartÄ± gÃ¼Ã§lendirildi
DISPLAY_MIN_CONF         = 0.40   # Ekranda gÃ¶sterilecek min. son gÃ¼ven
DISPLAY_MIN_CLASS_VOTE   = 0.60   # BUG-FIX: 0.55 â†’ 0.60 â€” titremeyi Ã¶nlemek iÃ§in eÅŸik artÄ±rÄ±ldÄ±
DISPLAY_MIN_HITS         = 2      # Ä°HA olarak ekrana Ã§Ä±kmak iÃ§in min. hit (uÃ§ak kÄ±sa gÃ¶rÃ¼nÃ¼yor)
DISPLAY_ALLOWED_CLASSES  = (1, 2) # ID=1 (KuÅŸ) ve ID=2 (UÃ§ak/Ä°HA) sÄ±nÄ±flarÄ±nÄ±n ikisi de iÅŸlenir
FRAGMENT_MERGE_GAP_RATIO = 0.35   # GÃ¶vde/kanat parÃ§alarÄ±nÄ± birleÅŸtirme mesafesi (oransal)

# BUG-FIX (KRÄ°TÄ°K â€” "dev kutu" / ekranÄ± kaplayan hayalet kutu):
# _merge_aircraft_fragments() eskiden YALNIZCA oransal boÅŸluÄŸa (yukarÄ±daki
# FRAGMENT_MERGE_GAP_RATIO) bakÄ±yordu: gap <= max(base.w, other.w) * 0.35.
# ParÃ§alardan biri zaten bÃ¼yÃ¼kse (Ã¶r. 800px), bu oran 280px'lik bir mutlak
# boÅŸluÄŸa bile "yakÄ±n" diyebiliyordu. Ã‡oklu-panel / split-screen / kolaj
# gÃ¶rÃ¼ntÃ¼lerde (Ã¶r. 2x2 kokpit Ä±zgarasÄ±) komÅŸu panolar TAM OLARAK bitiÅŸiktir
# (gapâ‰ˆ0px) ve her ikisinde de benzer ÅŸekiller (kask, ekran Ã§erÃ§evesi vb.)
# yanlÄ±ÅŸ pozitif "kuÅŸ/Ä°HA" tespiti Ã¼retebilir â€” bu iki baÄŸÄ±msÄ±z, birbirinden
# uzak yanlÄ±ÅŸ tespit sÄ±rf x/y hizalÄ± ve "yakÄ±n" sayÄ±ldÄ±ÄŸÄ± iÃ§in TEK, DEV bir
# kutuya birleÅŸtiriliyordu (ekranÄ±n 2 satÄ±rÄ±nÄ±/kadranÄ±nÄ± kaplayan kutu).
# ArtÄ±k oransal boÅŸluÄŸun yanÄ±na MUTLAK bir piksel tavanÄ± da eklendi â€” gÃ¶vde/
# kanat parÃ§alarÄ± gerÃ§ekte birkaÃ§ on piksel arayla bulunur, asla yÃ¼zlerce
# piksel deÄŸil. Ä°ki koÅŸul da (oran VE mutlak tavan) saÄŸlanmadan asla
# birleÅŸtirme yapÄ±lmaz. AyrÄ±ca birleÅŸim sonucu is_valid_geometry() ile
# yeniden doÄŸrulanÄ±r (bkz. slicer.py detect()) â€” sonuÃ§ kutu MAX_OBJECT_AREA_RATIO
# veya en/boy sÄ±nÄ±rlarÄ±nÄ± aÅŸarsa birleÅŸtirme iptal edilir, parÃ§alar ayrÄ± kalÄ±r.
FRAGMENT_MERGE_MAX_GAP_PX = 150    # BUG-FIX: 50 â†’ 150 â€” Kamera Ã¶nÃ¼ne gelmiÅŸ dev uÃ§aklarda parÃ§alar arasÄ± fiziksel boÅŸluk 100+ piksel olabilir

# BUG-FIX (KRÄ°TÄ°K â€” "dev kutu", 2. katman): YukarÄ±daki gap tavanÄ± tek baÅŸÄ±na
# yetersiz kalabiliyor: Ä°KÄ° panel/kadran TAM bitiÅŸikse (gap=0px, Ã¶r. bir TV
# yayÄ±n grafiÄŸinde Ã¼st Ã¼ste duran iki kokpit gÃ¶rÃ¼ntÃ¼sÃ¼) gap kontrolÃ¼ hiÃ§bir
# ÅŸey elemez â€” Ã§Ã¼nkÃ¼ fiziksel olarak gerÃ§ekten "gap=0". GerÃ§ek bir uÃ§ak/Ä°HA
# gÃ¶vde-kanat parÃ§asÄ± SAHI patch sÄ±nÄ±rÄ±nda ikiye bÃ¶lÃ¼ndÃ¼ÄŸÃ¼nde her PARÃ‡A kendi
# baÅŸÄ±na ufaktÄ±r (nesnenin sadece bir kÄ±smÄ±); parÃ§alardan biri zaten frame'in
# Ã¶nemli bir bÃ¶lÃ¼mÃ¼nÃ¼ (Ã¶rn. bir kadranÄ±n tamamÄ±nÄ±) kaplayacak kadar BÃœYÃœKSE,
# bu artÄ±k "aynÄ± nesnenin parÃ§asÄ±" deÄŸil, kendi baÅŸÄ±na baÄŸÄ±msÄ±z (muhtemelen
# yanlÄ±ÅŸ pozitif) bir tespittir ve birleÅŸtirmeye aday bile sayÄ±lmamalÄ±dÄ±r.
# Bu yÃ¼zden birleÅŸtirme adaylÄ±ÄŸÄ± iÃ§in her iki parÃ§anÄ±n da (geniÅŸlik VE
# yÃ¼kseklik) bu mutlak piksel sÄ±nÄ±rÄ±nÄ±n ALTINDA kalmasÄ± ÅŸart koÅŸuldu.
FRAGMENT_MAX_MERGE_INPUT_PX = 800  # BUG-FIX: 400 â†’ 800 â€” KamerayÄ± kaplayan devasa uÃ§ak tespitlerinin (parÃ§alarÄ±nÄ±n) birleÅŸmesi engellenmesin

# BUG-FIX (arada 2-3 kutu + anlÄ±k "KUÅ" etiketi): KuÅŸ/UÃ§ak gÃ¶rsel rozeti
# eskiden HER karede yalnÄ±zca o anki (tek karelik) sinyallere gÃ¶re yeniden
# hesaplanÄ±yordu. Tek bulanÄ±k/gÃ¼rÃ¼ltÃ¼lÃ¼ bir kare bile rozeti bir anlÄ±ÄŸÄ±na
# "KUÅ"a Ã§evirip hemen geri dÃ¶nebiliyordu. ArtÄ±k son N karenin Ã‡OÄUNLUK
# oyu gÃ¶steriliyor â€” gerÃ§ek bir tÃ¼r deÄŸiÅŸimi yine birkaÃ§ kare iÃ§inde
# yakalanÄ±r, ama tek karelik gÃ¼rÃ¼ltÃ¼ artÄ±k rozeti Ã§eviremez.
TYPE_LABEL_SMOOTH_WINDOW = 15      # BUG-FIX: 7 â†’ 15 â€” ani manevrada tek karelik kuÅŸ sinyali rozeti Ã§eviremez, 15 karede Ã§oÄŸunluk gerekir (~0.5s @30fps)

# --- HÄ±z Filtresi ---
# Hareketsiz yaprak/leke tespiti. Uzak hovering uÃ§aklar iÃ§in istisna var.
MIN_SPEED_PX_S       = 0.5   # Bu hÄ±zÄ±n altÄ±ndaki track'ler ÅŸÃ¼pheli (px/s) (YAKLAÅAN UÃ‡AKLAR Ä°Ã‡Ä°N DÃœÅÃœRÃœLDÃœ)
MIN_SPEED_CHECK_HITS = 5     # KaÃ§ frame sonra hÄ±z kontrolÃ¼ baÅŸlar

# --- SÄ±Ã§rama Filtresi ---
MAX_PLAUSIBLE_JUMP_PX = 400.0  # Bu kadar px'den fazla sÄ±Ã§rama = gÃ¼rÃ¼ltÃ¼

# --- Kenarda TakÄ±lÄ± Kalma Filtresi (yaprak/dal) ---
EDGE_MARGIN_PX      = 0    # EkranÄ±n kenar bÃ¶lgesi geniÅŸliÄŸi (piksel, yaprak/dal iÃ§in)
EDGE_MAX_FRAMES     = 6    # Bu kadar frame kenarda kalÄ±rsa at (VLM tetikleme Ã¶ncesi temizlik)

# ======================== KAMERA HAREKETÄ° (EGO-MOTION) =======
# BUG-FIX (videoya gÃ¶re deÄŸiÅŸen kutu titremesi): CameraMotionCompensator
# eskiden yalnÄ±zca >=5 eÅŸleÅŸen optik-akÄ±ÅŸ noktasÄ±yla bile medyan kaymayÄ±
# doÄŸrudan gÃ¼veniyordu. GÃ¶kyÃ¼zÃ¼ aÄŸÄ±rlÄ±klÄ± / dÃ¼ÅŸÃ¼k dokulu arka planlÄ±
# videolarda hem bulunan kÃ¶ÅŸe sayÄ±sÄ± azalÄ±yor hem kalan birkaÃ§ nokta
# gÃ¼rÃ¼ltÃ¼lÃ¼ oluyor â€” birkaÃ§ kÃ¶tÃ¼ nokta medyanÄ± kaydÄ±rÄ±p HER TRACK'in
# Kalman durumuna hatalÄ± bir kayma enjekte ediyordu (o video titriyor,
# dokulu arka planlÄ± diÄŸer video sorunsuz gÃ¶rÃ¼nÃ¼yordu).
CMC_MIN_RELIABLE_POINTS = 15      # Medyan kayma iÃ§in gereken min. gÃ¼venilir nokta
CMC_MAX_SHIFT_PX        = 80.0    # Bu deÄŸerden bÃ¼yÃ¼k kare-arasÄ± kayma gÃ¼venilmez sayÄ±lÄ±r, uygulanmaz

# ======================== GERÃ‡EK HAREKET DOÄRULAMA ============
# BUG-FIX (boÅŸluÄŸu %99 gÃ¼venle Ä°HA sanma, uzun sÃ¼re ekranda kalmasÄ±):
# Bu yarÄ±ÅŸmada (Teknofest SavaÅŸan Ä°HA) gerÃ§ek bir hedef HAVADA GERÃ‡EKTEN
# HAREKET EDER â€” sabit kanatlÄ± bir uÃ§ak/Ä°HA fiziksel olarak havada
# donup kalamaz. Eskiden "uzak hedef + >10 hit" tek baÅŸÄ±na anlÄ±k hÄ±z
# filtresini (MIN_SPEED_PX_S) TAMAMEN atlÄ±yordu ("hovering Ä°HA" istisnasÄ±)
# ve classify_bird_vs_aircraft()'taki "rijit gÃ¶vde" bonusu da SADECE
# "kanat Ã§Ä±rpma sinyali YOK" bilgisine bakÄ±yordu â€” ikisi de "hareketsiz"
# ile "gerÃ§ek bir uÃ§ak" ayrÄ±mÄ± yapamÄ±yordu. Sabit duran bir gÃ¶kyÃ¼zÃ¼/bulut/
# parazit hayaleti tam olarak bu iki boÅŸluktan sÄ±zÄ±p sÃ¼resiz biÃ§imde
# ekranda "UÃ‡AK/Ä°HA %99" olarak kalabiliyordu.
# Ã‡Ã¶zÃ¼m: Net yer deÄŸiÅŸtirme yerine son WORLD_PATH_WINDOW_S saniyedeki
# TOPLAM KAT EDÄ°LEN YOLU (dÃ¼nya Ã§erÃ§evesi, CMC uygulanmÄ±ÅŸ _pos_history
# Ã¼zerinden) Ã¶lÃ§Ã¼yoruz â€” bu, dÃ¶nerek/manevra ederek de olsa gerÃ§ek bir
# hareketi yakalar, ama sabit duran (net veya kÃ¼Ã§Ã¼k salÄ±nÄ±mlÄ±) bir
# hayaleti artÄ±k ele verir. Bu eÅŸiÄŸi geÃ§emeyen hedefler ne "hovering Ä°HA"
# istisnasÄ±ndan ne de "rijit gÃ¶vde" bonusundan yararlanamaz â€” VLM ayrÄ±ca
# ve baÄŸÄ±msÄ±z olarak hava aracÄ± olduÄŸunu onaylamadÄ±kÃ§a.
MIN_WORLD_PATH_PX_PER_S = 2.0     # Son pencerede beklenen min. toplam kat edilen yol (px/s eÅŸdeÄŸeri) (YAKLAÅAN UÃ‡AKLAR Ä°Ã‡Ä°N DÃœÅÃœRÃœLDÃœ)
WORLD_PATH_WINDOW_S     = 1.0     # Yol hesabÄ± iÃ§in geriye bakÄ±ÅŸ penceresi (saniye)

# ======================== HUD & EKRAN LEKESÄ° FÄ°LTRESÄ° =================
# YENÄ° MÄ°MARÄ° (Scale-Static / Alan ve Konum SabitliÄŸi):
# Kameraya doÄŸru dalÄ±ÅŸ yapan (bÃ¼yÃ¼yen) hedefleri korumak ve Ekrana yapÄ±ÅŸÄ±k (Watermark,
# Grafik, HUD) nesneleri silmek iÃ§in ikili test uygulanÄ±r.
# 1. Obje ekran Ã¼zerinde sabit mi? (Kamera dÃ¶nse bile watermark kÃ¶ÅŸede kalÄ±r)
# 2. Objenin kutu alanÄ± (bÃ¼yÃ¼klÃ¼ÄŸÃ¼) zamanla deÄŸiÅŸmiyor mu? (DalÄ±ÅŸ yapan uÃ§aÄŸÄ±n alanÄ± katlanarak artarken, grafiklerin boyutu hep aynÄ±dÄ±r).
HUD_STATIC_MAX_MOVEMENT_PX = 15.0 # (BBox geniÅŸliÄŸine gÃ¶re esnetilir) Ekran konumu titreme limiti
HUD_STATIC_WINDOW_S        = 1.0  # Ã–lÃ§Ã¼m penceresi (saniye)
HUD_STATIC_MAX_AREA_CHANGE = 0.20 # 1 Saniye iÃ§inde kutu alanÄ± %20'den daha az deÄŸiÅŸmiÅŸse SABÄ°T/SAHTE kabul edilir.

# YENÄ° MÄ°MARÄ° 2: (Solid-Body / Otsu DengesizliÄŸi Filtresi)
# EÄŸer bir HUD grafiÄŸi (Ã–rn: CROWD yazÄ±sÄ±) videonun iÃ§ine yedirilmiÅŸse ve 50px/s ile hareket ediyorsa,
# yukarÄ±daki konum sabitliÄŸi kuralÄ±ndan yÄ±rtar! Ancak yazÄ±lar (harfler, ince Ã§izgiler) Bounding Box'Ä±n
# iÃ§ini asla DOLDURAMAZ (Sadece %1-%3 alan kaplarlar). GerÃ§ek uÃ§ak gÃ¶vdesi ise en az %10 kaplar.
MIN_SOLID_BODY_RATIO = 0.04 # Bir objenin UÃ§ak sayÄ±lmasÄ± iÃ§in Otsu maskesinde en az %4 alan kaplamasÄ± zorunludur.

# ======================== ASKIDAKÄ° (SUSPENDED) KUTU Ã‡Ä°ZÄ°MÄ° =====
# BUG-FIX (kutu havada geziniyor / uÃ§aÄŸÄ±n gittiÄŸi yerle alakasÄ± yok):
# Tespit birkaÃ§ kare kaybolduÄŸunda track "suspended" moduna girip
# KALMAN_SUSPENDED_AGE (45 kare, ~1.5-1.8sn) boyunca salt DOÄžRUSAL HIZ
# MODELÄ°YLE ekstrapolasyon yapÄ±yordu ve bu tahmini kutu HÃ‚LÃ‚ TAM GÃœVENLE
# (dolu Ã§izgi, tam opaklÄ±k) Ã§iziliyordu. Hedef manevra/dÃ¶nÃ¼ÅŸ yaptÄ±ÄŸÄ±nda
# doÄŸrusal model gerÃ§ek pozisyondan hÄ±zla sapÄ±yor, kullanÄ±cÄ± ekranda
# "kutu boÅŸlukta geziniyor" gÃ¶rÃ¼yordu. ArtÄ±k: iÃ§ takip/kimlik koruma
# (re-id) hÃ¢lÃ¢ KALMAN_SUSPENDED_AGE kadar sÃ¼rÃ¼yor (kimlik kaybÄ±nÄ± Ã¶nlemek
# iÃ§in bu iyi ve korunuyor), AMA gÃ¶rsel Ã§izim yalnÄ±zca kÄ±sa bir "zarif
# bekleme" sÃ¼resi kadar tam gÃ¼venle gÃ¶steriliyor; sonrasÄ±nda track yeniden
# gerÃ§ek bir tespit alana kadar EKRANDAN GÄ°ZLENÄ°YOR (belirsiz/gÃ¼venilmez
# bir tahmini konumu kesin bir tehdit kutusu gibi gÃ¶stermek yerine).
SUSPENDED_DRAW_GRACE_FRAMES = 15   # BUG-FIX: 75 â†’ 15 â€” oklÃ¼zyon sonrasÄ± salt Kalman tahminini ~0.5s sonra gizle, havada gezen kutu Ã¶nlenir

# ======================== GÃ–RÃœNTÃœ Ä°YÄ°LEÅžTÄ°RME ===============
CLAHE_CLIP       = 2.0
CLAHE_GRID       = (8, 8)
SHARPEN_STRENGTH = 1.5
MIN_CROP_SIZE    = 8

# --- GPU Enhancer ---
# CUDA varsa GPU yolunu kullan; yoksa veya cv2.cuda yoksa CPU'ya dÃ¼ÅŸ.
USE_GPU_ENHANCE  = True       # False â†’ CPU'yu zorla (debug/karÅŸÄ±laÅŸtÄ±rma iÃ§in)
# CLAHE parametreleri â€” VLM'i bozmayan hafif ayar:
#   clip=1.5 (>2.0 VLM'i yanÄ±ltÄ±yor), tile=16Ã—16 (ince yerel kontrast)
CLAHE_CLIP_GPU   = 1.5
CLAHE_GRID_GPU   = (16, 16)
# KaranlÄ±k krop'lar iÃ§in hafif gamma dÃ¼zeltme (1.0 = kapalÄ±)
ENHANCE_GAMMA    = 1.1

# --- Kolaj (build_visual_grid) ---
COLLAGE_CELL_SIZE  = 384      # Her hÃ¼crenin piksel boyutu
COLLAGE_BORDER_PX  = 3        # HÃ¼creler arasÄ± ince gri Ã§izgi (px)
COLLAGE_BG_COLOR   = (30, 30, 30)  # Siyah deÄŸil koyu gri zemin â€” VLM gece sanmasÄ±n

# ======================== VLM ================================
# dÃ¼ÅŸÃ¼nmeye token hÄ±rcar, JSON Ã§Ä±kmaz.
VLM_MODEL_NAME             = "qwen2.5vl:7b"
VLM_API_URL                = "http://localhost:11434/api/generate"
VLM_NUM_PREDICT            = 1024   # KÄ±sa ve Ã¶z JSON cevaplarÄ± iÃ§in yeterli
VLM_TIMEOUT_S              = 300.0  # 5 dakika timeout (YavaÅŸ bilgisayarlar iÃ§in artÄ±rÄ±ldÄ±)
VLM_MIN_RECALL_INTERVAL_S  = 0.7    # [GÃœNCELLENDÄ°] 3.0->0.7: UÃ§ak aniden yakÄ±nlaÅŸÄ±p inanÄ±lmaz net bir kare (Ã¶rnekteki F-4 kuyruÄŸu gibi) verirse 3 saniye bekleme, hemen 0.7 sn iÃ§inde VLM'i tetikle!
# BUG-FIX: VLM_MIN_RECALL_INTERVAL_S eskiden vlm_engine.py iÃ§inde AYNI ZAMANDA
# genel spam-koruma cooldown'u olarak da kullanÄ±lÄ±yordu. YukarÄ±daki deÄŸer
# 3.0'dan 0.7'ye dÃ¼ÅŸÃ¼rÃ¼lÃ¼nce (pipeline.py'deki "sÃ¼per kare" hÄ±zlÄ± yeniden-
# tetikleme amacÄ±yla), vlm_engine.py'nin aynÄ± track_id'yi Ollama'ya spamlemesini
# Ã¶nleyen koruma da istemeden 0.7s'e zayÄ±flamÄ±ÅŸ oluyordu. Ä°ki amaÃ§ artÄ±k ayrÄ±
# sabitlerle yÃ¶netiliyor â€” bu sabit SADECE vlm_engine.py'nin motor-seviyesi
# spam korumasÄ±nÄ± kontrol eder, pipeline.py'nin recall mantÄ±ÄŸÄ±nÄ± etkilemez.
VLM_ENGINE_MIN_CALL_INTERVAL_S = 1.5  # BUG-FIX: 3.0 â†’ 1.5 â€” pipeline'Ä±n 0.7s recall mantÄ±ÄŸÄ±yla uyumlu, Ollama spam korumasÄ± yeterli
VLM_RECALL_IQA_GAIN        = 1.10   # [GÃœNCELLENDÄ°] 1.15->1.10: Yeni fotoÄŸraf %10 daha net/keskin ise hemen VLM'i gÃ¼ncelle.
                                     # (eskiden pipeline.py iÃ§inde sabit 1.25 idi â€” biraz sÄ±kÄ±ydÄ±, artÄ±k config'ten yÃ¶netiliyor)
VLM_VOTE_WINDOW            = 5
VLM_COOLDOWN_S             = 0.5   # VLM Ã§aÄŸrÄ±larÄ± arasÄ± minimum sÃ¼re
VLM_MIN_BBOX_PX            = 15    # Hedefin VLM'e gitmesi iÃ§in en az 15px olmasÄ±nÄ± bekle.
VLM_MIN_CONFIDENCE_FOR_TIP = 40    # GÃ¼ven eÅŸiÄŸi (0-100), altÄ± â†’ tanÄ±msÄ±z
VLM_MIN_TRACK_CONF         = 0.35  # Track gÃ¼veni bunun altÄ±ndaysa VLM Ã§alÄ±ÅŸmaz
VLM_CROP_CONTEXT_RATIO     = 0.25  # Prensip 3 (Smart Crop): UÃ§aÄŸÄ±n tamamÄ±nÄ± ve Ã§evresini almak iÃ§in %25 padding
VLM_CROP_MIN_CONF          = 0.30  # Keyframe tamponuna kabul eÅŸiÄŸi
# FarklÄ± aÃ§Ä±lardan (dÃ¶nÃ¼ÅŸ, dalÄ±ÅŸ, yan silÃ¼et) en zengin aday havuzunu toplamak iÃ§in geniÅŸ tampon
VLM_CROP_BUFFER_SIZE       = 45
# KaÃ§ frame gÃ¶rÃ¼ldÃ¼kten sonra kolaj VLM'e gÃ¶nderilsin (Ã§ok kÄ±sa track'leri filtreler)
# NOT: Bu tek baÅŸÄ±na yeterli deÄŸil â€” bkz. VLM_MIN_CROP_POOL_SIZE. hits sadece
# "track ne kadar sÃ¼redir yaÅŸÄ±yor"yu Ã¶lÃ§er, buffer'Ä±n gerÃ§ekten dolup dolmadÄ±ÄŸÄ±nÄ± deÄŸil.
VLM_MIN_HITS_FOR_COLLAGE   = 8

# BUG-FIX (en kÃ¶tÃ¼ kare sorunu): Eskiden VLM, hedef daha 8. frame'de (~0.27sn)
# gÃ¶rÃ¼lÃ¼r gÃ¶rÃ¼lmez tetikleniyordu. O anda _crop_buffer'da genelde 3-6 kare vardÄ±
# (hedef henÃ¼z uzak/bulanÄ±k/kÃ¶tÃ¼ aÃ§Ä±da). "En iyisini seÃ§" doÄŸru Ã§alÄ±ÅŸÄ±yordu ama
# Ã§ok kÃ¼Ã§Ã¼k ve kÃ¶tÃ¼ bir havuzun en iyisini seÃ§iyordu. Åžimdi VLM, track'in kendi
# kalite-filtrelenmiÅŸ buffer'Ä± bu kadar kareyle dolana kadar BEKLÄ°YOR â€” bÃ¶ylece
# hedef ekranda gezinirken (yaklaÅŸma, dÃ¶nÃ¼ÅŸ, yan silÃ¼et) toplanan gerÃ§ekten
# zengin bir havuzdan seÃ§im yapÄ±lÄ±yor.
# BUG-FIX (VLM hiÃ§ tetiklenmiyordu): 18, track'ler kÄ±sa Ã¶mÃ¼rlÃ¼/bÃ¶lÃ¼nmÃ¼ÅŸ
# olduÄŸunda (bkz. slicer.py _dedupe_overlapping_targets dÃ¼zeltmesi) VEYA
# gÃ¶rÃ¼ntÃ¼ kalitesi sÄ±nÄ±rdayken pratikte hiÃ§ dolmuyordu. 10'a Ã§ekildi â€”
# hÃ¢lÃ¢ "birkaÃ§ karenin en iyisi" deÄŸil, gerÃ§ek bir zengin havuz, ama
# artÄ±k ulaÅŸÄ±labilir.
VLM_MIN_CROP_POOL_SIZE     = 10   # _crop_buffer'da birikmesi gereken min. kaliteli kare

VLM_VOTE_WINDOW            = 5
VLM_COOLDOWN_S             = 0.5   # VLM Ã§aÄŸrÄ±larÄ± arasÄ± minimum sÃ¼re
VLM_MIN_BBOX_PX            = 15    # Hedefin VLM'e gitmesi iÃ§in en az 15px olmasÄ±nÄ± bekle.
# ======================== TEHDÄ°T SKORU =======================
VLM_MIN_CONFIDENCE_FOR_TIP = 40    # GÃ¼ven eÅŸiÄŸi (0-100), altÄ± â†’ tanÄ±msÄ±z
VLM_MIN_TRACK_CONF         = 0.35  # Track gÃ¼veni bunun altÄ±ndaysa VLM Ã§alÄ±ÅŸmaz
VLM_CROP_CONTEXT_RATIO     = 0.25  # Prensip 3 (Smart Crop): UÃ§aÄŸÄ±n tamamÄ±nÄ± ve Ã§evresini almak iÃ§in %25 padding
VLM_CROP_MIN_CONF          = 0.30  # Keyframe tamponuna kabul eÅŸiÄŸi
# FarklÄ± aÃ§Ä±lardan (dÃ¶nÃ¼ÅŸ, dalÄ±ÅŸ, yan silÃ¼et) en zengin aday havuzunu toplamak iÃ§in geniÅŸ tampon
VLM_CROP_BUFFER_SIZE       = 45
# KaÃ§ frame gÃ¶rÃ¼ldÃ¼kten sonra kolaj VLM'e gÃ¶nderilsin (Ã§ok kÄ±sa track'leri filtreler)
# NOT: Bu tek baÅŸÄ±na yeterli deÄŸil â€” bkz. VLM_MIN_CROP_POOL_SIZE. hits sadece
# "track ne kadar sÃ¼redir yaÅŸÄ±yor"yu Ã¶lÃ§er, buffer'Ä±n gerÃ§ekten dolup dolmadÄ±ÄŸÄ±nÄ± deÄŸil.
VLM_MIN_HITS_FOR_COLLAGE   = 8

# BUG-FIX (en kÃ¶tÃ¼ kare sorunu): Eskiden VLM, hedef daha 8. frame'de (~0.27sn)
# gÃ¶rÃ¼lÃ¼r gÃ¶rÃ¼lmez tetikleniyordu. O anda _crop_buffer'da genelde 3-6 kare vardÄ±
# (hedef henÃ¼z uzak/bulanÄ±k/kÃ¶tÃ¼ aÃ§Ä±da). "En iyisini seÃ§" doÄŸru Ã§alÄ±ÅŸÄ±yordu ama
# Ã§ok kÃ¼Ã§Ã¼k ve kÃ¶tÃ¼ bir havuzun en iyisini seÃ§iyordu. Åimdi VLM, track'in kendi
# kalite-filtrelenmiÅŸ buffer'Ä± bu kadar kareyle dolana kadar BEKLÄ°YOR â€” bÃ¶ylece
# hedef ekranda gezinirken (yaklaÅŸma, dÃ¶nÃ¼ÅŸ, yan silÃ¼et) toplanan gerÃ§ekten
# zengin bir havuzdan seÃ§im yapÄ±lÄ±yor.
# BUG-FIX (VLM hiÃ§ tetiklenmiyordu): 18, track'ler kÄ±sa Ã¶mÃ¼rlÃ¼/bÃ¶lÃ¼nmÃ¼ÅŸ
# olduÄŸunda (bkz. slicer.py _dedupe_overlapping_targets dÃ¼zeltmesi) VEYA
# gÃ¶rÃ¼ntÃ¼ kalitesi sÄ±nÄ±rdayken pratikte hiÃ§ dolmuyordu. 10'a Ã§ekildi â€”
# hÃ¢lÃ¢ "birkaÃ§ karenin en iyisi" deÄŸil, gerÃ§ek bir zengin havuz, ama
# artÄ±k ulaÅŸÄ±labilir.
VLM_MIN_CROP_POOL_SIZE     = 10   # _crop_buffer'da birikmesi gereken min. kaliteli kare

# BUG-FIX (Ã§ift tanÄ±m): Bu deÄŸiÅŸken eskiden iki kere tanÄ±mlanÄ±yordu (Ã¶nce 1,
# sonra buradaki 4 onu eziyordu) â€” Ã§eliÅŸen iki yorum, hangisinin aktif
# olduÄŸunu belirsizleÅŸtiriyordu. Tek tanÄ±ma indirildi, deÄŸer (4) korunuyor.
# 4 farklÄ± aÃ§Ä±dan en iyi fotoÄŸraflarÄ± 2x2 grid (kolaj) olarak VLM'e gÃ¶nderir;
# 1 yapÄ±lÄ±rsa build_visual_grid otomatik olarak tek kare gÃ¶nderime dÃ¶ner.
VLM_CROP_SEND_COUNT        = 4

# ======================== TEHDÄ°T SKORU =======================
THREAT_WEIGHT_CLASS  = 2.0
THREAT_WEIGHT_CONF   = 1.0
THREAT_WEIGHT_SIZE   = 5.0
THREAT_WEIGHT_CENTER = 0.5

# ======================== SAHNE ==============================
SCENE_CHANGE_THRESHOLD = 40.0
ARENA_POLYGON          = []   # [] = tÃ¼m frame arena

# ======================== Ã‡IKTI ==============================
# INFO-2 DÃ¼zeltmesi: Mutlak path kullanÄ±lÄ±yor â€” Ã§alÄ±ÅŸma dizininden baÄŸÄ±msÄ±z.
OUTPUT_DIR    = Path(__file__).parent.parent / "output"
DEBUG_VLM_DIR = OUTPUT_DIR / "debug_vlm"
DEBUG_RAG_DIR = OUTPUT_DIR / "debug_rag"
SHOW_WINDOW   = True
SAVE_VIDEO    = False

# ======================== VRAG (GÃ–RSEL HAFIZA) =======================
VRAG_ENABLED         = True
VRAG_DB_PATH         = OUTPUT_DIR / "qdrant_db"
VRAG_COLLECTION_NAME = "uav_knowledge"
SIGLIP_MODEL_NAME    = "google/siglip2-so400m-patch14-384"
VRAG_MIN_SCORE       = 0.65  # EÅŸleÅŸme iÃ§in minimum Cosine Similarity
# Zamansal oylama: VRAG'in bagimsiz canli aramasi track basina saniyede bir
# calisir, tek karenin sonucu titreyebilir (ayni hedef icin art arda farkli
# modeller). Son VRAG_VOTE_WINDOW aramanin en sik tekrar eden top-1 modeli
# gosterilir - VLM tarafindaki TrackVoteAggregator ile ayni mantik.
VRAG_VOTE_WINDOW     = 5
# ======================== VRAG VERİ ARTIRMA (AUGMENTATION) ===
DONME_ACILARI        = (-12, 12)
OLCEK_FAKTORLERI     = (0.8, 0.5, 0.25)
BULANIKLIK_YARICAPI  = 1.2
PERSPEKTIF_AKTIF     = True

# ======================== FPS OPTİMİZASYONU =======================
# Akıllı kare atlama: YOLO çıkarımı bütçeyi aşarsa sonraki kare(ler)de
# sadece Kalman tahmin kullanılır, YOLO atlanır.
ADAPTIVE_SKIP_ENABLED   = True
ADAPTIVE_SKIP_BUDGET_MS = 45    # Frame başına YOLO bütçesi (ms). Aşılırsa sonraki frame atlanır
FRAME_READ_BUFFER_SIZE  = 4     # Ön-okuma thread tamponu (frame sayısı)

# ======================== VLM SAĞLAMLIK ===========================
# llava-phi3 gibi küçük multimodal modeller format:"json" parametresiyle
# boş yanıt verebilir. Bu ayar kapatıldığında JSON parse kendi yapılır.
VLM_FORCE_JSON_FORMAT   = False  # True: Ollama'ya format:"json" gönder. False: ham çıktıyı parse et
VLM_RETRY_ON_EMPTY      = True   # Boş/geçersiz yanıtta 1 kere tekrar dene
VLM_RETRY_DELAY_S       = 1.0    # Tekrar deneme öncesi bekleme süresi (saniye)

# ======================== LLM (OPERASİYONEL KARAR) ================
LLM_ENABLED          = True
LLM_API_URL           = "http://127.0.0.1:8000"
LLM_TIMEOUT_S         = 30.0    # LLM API çağrısı timeout süresi (saniye)
LLM_RETRY_COUNT       = 1       # Hata durumunda tekrar deneme sayısı
# LLM servisini subprocess olarak otomatik başlat
LLM_AUTO_START        = True
LLM_PROJECT_DIR       = str(Path(__file__).parent.parent / "LLM")
LLM_VENV_DIR          = str(Path(__file__).parent.parent / "LLM" / ".venv")
LLM_HOST              = "127.0.0.1"
LLM_PORT              = 8000

