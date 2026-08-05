import requests, json

payload = {
    "model": "minicpm-v",
    "format": "json",
    "messages": [{"role": "user", "content": "You are an aircraft analyst. Analyze the image and return ONLY JSON with these exact keys: visual_analysis (string), arac_sinifi (one of: sabit_kanat/doner_kanat/kus/bilinmeyen), tehdit_seviyesi (one of: yuksek/orta/dusuk/yok), tahmini_hedef_tipi (one of: kamikaze/siha/iha/askeri_ucak/yolcu_ucagi/gozetleme/ticari_drone/dogal_yasam/tanimsiz), ulke_orjini (string), hedef_modeli (string), gorsel_analiz (string)."}],
    "stream": False
}
r = requests.post("http://localhost:11434/api/chat", json=payload, timeout=30)
data = r.json()
content = data.get("message", {}).get("content", "")
print("RAW CONTENT:", content[:500])
try:
    parsed = json.loads(content)
    print("JSON OK! Keys:", list(parsed.keys()))
except Exception as e:
    print("JSON FAIL:", e)
