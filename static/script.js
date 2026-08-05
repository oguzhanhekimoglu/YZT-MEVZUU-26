"use strict";

const $ = (id) => document.getElementById(id);
let durumData = null;

// --- Ortak fetch ---
async function istek(url, govde) {
  const opts = govde
    ? { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(govde) }
    : {};
  const r = await fetch(url, opts);
  const v = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(v.hata || "HTTP " + r.status);
  return v;
}

function hataGoster(msg) {
  $("hata").textContent = "Hata: " + msg;
  $("hata").hidden = false;
}

function mesgul(goster, metin) {
  if (goster) $("hata").hidden = true;
  $("yukleniyor-metin").textContent = metin || "Analiz ediliyor…";
  $("yukleniyor").hidden = !goster;
  ["indeksle-btn", "benchmark-btn", "tani-btn"].forEach((id) => {
    const el = $(id);
    if (el) el.disabled = goster;
  });
  if (!goster) taniButonDurum();
}

function taniButonDurum() {
  $("tani-btn").disabled = !$("dosya").files[0];
}

// --- Durum ---
function rozetGuncelle() {
  const var_ = !!(durumData && durumData.indeksli);
  const rozet = $("encoder-rozet");
  rozet.textContent = var_ ? "indeksli" : "indeks yok";
  rozet.className = "rozet-durum " + (var_ ? "var" : "yok");
}

async function durumYukle() {
  durumData = await istek("/durum");
  rozetGuncelle();
  $("kontrol-durum").innerHTML = durumData.indeksli
    ? `Aktif: <b>${durumData.encoder}</b> · indeks hazır`
    : `<b>${durumData.encoder}</b> indekslenmemiş — “Yeniden İndeksle”ye bas.`;
}

// --- Yeniden indeksle ---
$("indeksle-btn").addEventListener("click", async () => {
  mesgul(true, "İndeksleniyor (birkaç dakika sürebilir)…");
  try {
    const v = await istek("/indeksle", {});
    await durumYukle();
    $("kontrol-durum").innerHTML =
      `İndekslendi: ${v.model_klasoru} model · ${v.vektor} vektör · ${v.sure} sn.`;
  } catch (e) {
    hataGoster(e.message);
  } finally {
    mesgul(false);
  }
});

// --- Benchmark ---
$("benchmark-btn").addEventListener("click", async () => {
  mesgul(true, "Benchmark çalışıyor (retrieval)…");
  try {
    const v = await istek("/benchmark", {});
    benchmarkSatirEkle(v);
  } catch (e) {
    hataGoster(e.message);
  } finally {
    mesgul(false);
  }
});

function benchmarkSatirEkle(v) {
  const tb = document.querySelector("#benchmark-tablo tbody");
  const bos = tb.querySelector(".bos");
  if (bos) bos.remove();
  const tr = document.createElement("tr");
  tr.className = "yeni";
  tr.innerHTML =
    `<td>${v.encoder}</td>` +
    `<td><span class="metrik">%${v.top1_yuzde}</span> <span class="alt">(${v.top1}/${v.n})</span></td>` +
    `<td>%${v.top3_yuzde}</td><td>${v.sure} sn</td>`;
  tb.prepend(tr);
}

// --- Yükleme / önizleme ---
const dosya = $("dosya"), birak = $("birak"), onizleme = $("onizleme"),
  onizlemeBos = $("onizleme-bos");

function dosyaSecildi(f) {
  if (!f) return;
  onizleme.src = URL.createObjectURL(f);
  onizleme.hidden = false;
  onizlemeBos.hidden = true;
  taniButonDurum();
}
dosya.addEventListener("change", () => dosyaSecildi(dosya.files[0]));
["dragover", "dragenter"].forEach((e) =>
  birak.addEventListener(e, (ev) => { ev.preventDefault(); birak.classList.add("aktif"); }));
["dragleave", "drop"].forEach((e) =>
  birak.addEventListener(e, (ev) => { ev.preventDefault(); birak.classList.remove("aktif"); }));
birak.addEventListener("drop", (ev) => {
  const f = ev.dataTransfer.files[0];
  if (f) { dosya.files = ev.dataTransfer.files; dosyaSecildi(f); }
});

// --- Tanı ---
$("form").addEventListener("submit", async (ev) => {
  ev.preventDefault();
  if (!dosya.files[0]) return;
  $("sonuc").hidden = true;
  mesgul(true, "Analiz ediliyor… (retrieval)");
  try {
    const fd = new FormData();
    fd.append("gorsel", dosya.files[0]);
    fd.append("ulke", $("filtre-ulke").value);
    fd.append("rol", $("filtre-rol").value);
    const r = await fetch("/tani", { method: "POST", body: fd });
    const v = await r.json();
    if (!r.ok) throw new Error(v.hata || "Sunucu hatası");
    sonucGoster(v);
  } catch (e) {
    hataGoster(e.message);
  } finally {
    mesgul(false);
  }
});

function sonucGoster(v) {
  $("sonuc-gorsel").src = v.sorgu;
  $("secilen-model").textContent = v.tahmin.model;
  $("sonuc-config").textContent = `· ${v.encoder}`;
  const t = v.tahmin;
  const meta = [t.ulke, t.uretici, t.rol, t.motor ? t.motor + " motor" : ""].filter(Boolean);
  $("tahmin-meta").textContent = meta.join(" · ");
  const yuzde = Math.round(v.tahmin.skor * 100);
  $("guven-dolu").style.width = yuzde + "%";
  $("guven-yuzde").textContent = "%" + yuzde + " benzerlik";
  $("dusuk-guven-uyari").hidden = !v.tahmin.dusuk_guven;
  const ozellik = v.tahmin.ozellik || "";
  $("gerekce").textContent = ozellik;
  $("ozellik-baslik").hidden = !ozellik;

  const grid = $("adaylar");
  grid.innerHTML = "";
  v.adaylar.forEach((a) => {
    const skorY = Math.round(a.skor * 100);
    const secili = a.sira === 1 ? " secilen" : "";
    const kart = document.createElement("div");
    kart.className = "aday-kart" + secili;
    const altBilgi = [a.kategori, a.ulke].filter(Boolean).join(" · ");
    kart.innerHTML =
      `<img src="${a.gorsel}" alt="" loading="lazy">` +
      `<div class="aday-bilgi"><b>${a.sira}. ${a.model}</b>` +
      `<span class="kategori">${altBilgi}</span>` +
      `<div class="skor-bar"><div style="width:${skorY}%"></div></div>` +
      `<small>benzerlik ${a.skor.toFixed(4)}</small></div>`;
    grid.appendChild(kart);
  });
  $("sonuc").hidden = false;
  $("sonuc").scrollIntoView({ behavior: "smooth", block: "start" });
}

// --- Başlangıç ---
durumYukle().catch((e) => hataGoster(e.message));
