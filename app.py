"""VRAG web arayüzü — Flask (tek encoder, retrieval-only).

Fotoğraf yükle → en benzer hava aracı modeli (retrieval top-1) + adaylar + güven.
Benchmark (leave-one-out) doğruluğu ölçer. Nihai tahmin = retrieval top-1.

Çalıştırma:  python app.py   →  http://127.0.0.1:5000
"""
from __future__ import annotations

import json
import threading
import time
from pathlib import Path
from urllib.parse import quote

from flask import Flask, abort, jsonify, render_template, request, send_file

from vrag import config, degerlendirme, indeksleme
from vrag.arama import ara, dusuk_guven, margin
from vrag.gomleme import gomleyici_al
from vrag.vektor_deposu import VektorDeposu, indeks_var

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 16 * 1024 * 1024

_kilit = threading.Lock()

YUKLEME_DIZINI = config.PROJE_KOK / "yuklemeler"
YUKLEME_DIZINI.mkdir(exist_ok=True)
_IZINLI_KOKLER = [config.VERI_DIZINI.resolve(), YUKLEME_DIZINI.resolve()]

_depo: dict = {"d": None}   # tek yerleşik VektorDeposu


def _depo_al() -> VektorDeposu:
    if _depo["d"] is None:
        _depo["d"] = VektorDeposu()
    return _depo["d"]


def _encoder_ad() -> str:
    return config.ENCODER_MODELI.split("/")[-1]


# --- Yardımcılar ------------------------------------------------------------
def _izinli(p: Path) -> bool:
    try:
        p = p.resolve()
    except OSError:
        return False
    return any(p.is_relative_to(kok) for kok in _IZINLI_KOKLER)


def _gorsel_url(yol) -> str:
    return "/gorsel?yol=" + quote(str(yol))


def _model_sayisi() -> int:
    kok = config.VERI_DIZINI
    if not kok.exists():
        return 0
    return sum(
        1 for p in kok.rglob("*")
        if p.is_dir() and any(
            c.suffix.lower() in config.DESTEKLENEN_UZANTILAR for c in p.iterdir() if c.is_file()
        )
    )


def _distinct_meta(alan: str) -> list[str]:
    """metadata.json'lardan bir alanın (ör. ulke/rol) farklı değerlerini toplar."""
    degerler: set[str] = set()
    for mp in config.VERI_DIZINI.rglob("metadata.json"):
        try:
            v = json.loads(mp.read_text(encoding="utf-8")).get(alan)
        except (OSError, ValueError):
            continue
        if v:
            degerler.add(str(v))
    return sorted(degerler)


# --- Sayfa & uçlar ----------------------------------------------------------
@app.route("/")
def anasayfa():
    return render_template(
        "index.html",
        model_sayisi=_model_sayisi(),
        encoder=_encoder_ad(),
        ulkeler=_distinct_meta("ulke"),
        roller=_distinct_meta("rol"),
    )


@app.route("/durum")
def durum():
    return jsonify({"encoder": _encoder_ad(), "indeksli": indeks_var()})


@app.route("/indeksle", methods=["POST"])
def indeksle():
    try:
        with _kilit:
            # rmtree açık DB'yi silemez -> önce depoyu kapat.
            if _depo["d"] is not None:
                _depo["d"].kapat()
                _depo["d"] = None
            t0 = time.time()
            son = indeksleme.calistir(dizin=config.VERI_DIZINI)
            ozet = {"model_klasoru": son["model_klasoru"], "vektor": son["vektor"],
                    "sure": round(time.time() - t0)}
    except Exception as e:
        return jsonify({"hata": str(e)}), 500
    return jsonify(ozet)


@app.route("/benchmark", methods=["POST"])
def benchmark():
    try:
        with _kilit:
            if not indeks_var():
                return jsonify({"hata": "İndeks kurulu değil. Önce 'Yeniden İndeksle'."}), 409
            t0 = time.time()
            sonuc = {"encoder": _encoder_ad()}
            sonuc.update(degerlendirme.retrieval_dogruluk(depo=_depo_al()))
            sonuc["sure"] = round(time.time() - t0)
    except Exception as e:
        return jsonify({"hata": str(e)}), 500
    return jsonify(sonuc)


@app.route("/tani", methods=["POST"])
def tani():
    dosya = request.files.get("gorsel")
    if dosya is None or dosya.filename == "":
        return jsonify({"hata": "Görsel seçilmedi."}), 400

    uzanti = Path(dosya.filename).suffix.lower()
    if uzanti not in config.DESTEKLENEN_UZANTILAR:
        return jsonify({"hata": f"Desteklenmeyen dosya türü: {uzanti}"}), 400

    hedef = YUKLEME_DIZINI / f"sorgu{uzanti}"
    dosya.save(hedef)

    # Opsiyonel filtreler (arayüz dropdown'ları): boşsa yok sayılır.
    ulke = request.form.get("ulke") or None
    rol = request.form.get("rol") or None

    try:
        with _kilit:
            if not indeks_var():
                return jsonify({"hata": "İndeks kurulu değil. Önce 'Yeniden İndeksle'."}), 409
            adaylar = ara(hedef, topk=config.VARSAYILAN_TOPK, depo=_depo_al(),
                          ulke=ulke, rol=rol)
    except Exception as e:
        return jsonify({"hata": str(e)}), 500

    if not adaylar:
        return jsonify({"hata": "Bu filtrelerle eşleşme bulunamadı."}), 404

    return jsonify({
        "sorgu": _gorsel_url(hedef),
        "encoder": _encoder_ad(),
        "filtre": {"ulke": ulke, "rol": rol},
        # Nihai tahmin = retrieval top-1 (en yüksek benzerlik).
        "tahmin": {
            "model": adaylar[0].model,
            "kategori": adaylar[0].kategori,
            "skor": round(adaylar[0].skor, 4),
            "ozellik": adaylar[0].ayirt_edici_ozellikler,
            "ulke": adaylar[0].ulke,
            "uretici": adaylar[0].uretici,
            "rol": adaylar[0].rol,
            "motor": adaylar[0].motor_sayisi,
            "dusuk_guven": dusuk_guven(adaylar),
            "margin": round(margin(adaylar), 4),
        },
        "adaylar": [
            {"sira": i + 1, "model": a.model, "skor": round(a.skor, 4),
             "kategori": a.kategori, "ulke": a.ulke, "rol": a.rol,
             "gorsel": _gorsel_url(a.referans_yolu)}
            for i, a in enumerate(adaylar)
        ],
    })


@app.route("/gorsel")
def gorsel():
    yol = request.args.get("yol", "")
    if not yol:
        abort(400)
    p = Path(yol)
    if not p.is_absolute():
        p = config.PROJE_KOK / p
    if not _izinli(p) or not p.is_file():
        abort(404)
    return send_file(p)


def _isit() -> None:
    print(f"Encoder yükleniyor — {config.ENCODER_MODELI} (ilk açılış ~20 sn)...", flush=True)
    gomleyici_al()
    print("Hazır → http://127.0.0.1:5000", flush=True)


if __name__ == "__main__":
    _isit()
    app.run(host="127.0.0.1", port=5000, debug=False)
