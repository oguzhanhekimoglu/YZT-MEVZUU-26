# Upstream VLM Integration

API canonical `AnalyzeEventRequest` kabul eder. Raw Türkçe upstream payload önce `UpstreamVLMAdapter`, ardından canonical visual wrapper doğrulamasından geçer. Canonical örnekler `examples/upstream_vlm_payload.json`, `examples/visual_evidence_wrapper.json` ve `examples/analyze_event_request.json` altındadır.

Görsel hipotez kesin kimlik değildir. `visual_class`, `final_visual_hypothesis`, candidate bilgileri, timing ve producer metadata ayrı alanlardır. Unknown enum, bilinmeyen extra field ve timezone bilgisi olmayan datetime reddedilir. Invalid input HTTP 422 üretse de sanitized raw audit saklanır.

## Runtime mode sınırı

`data/seeds/raw_vlm_context_routes.json` yalnız `DEMO` modunun geçici mock yönlendirmesidir. `PRODUCTION` platform kimliğinden video context seçmez; upstream kaynak gerçek `video_id`, `track_id`, zaman aralığı ve operasyonel context sağlamalıdır. Gerekli context yoksa `CONTEXT_MISSING` davranışı korunur. Video event timestamp bilgisi yoksa değer uydurulmaz ve NOTAM geçerlilik zamanı video timestamp olarak kullanılmaz. Görsel güven upstream girdide yoksa production sabit `0.50` üretmez; contract gereği açık validation hatası verir.

LLM yalnız doğrulanmış evidence paketini Türkçe açıklama, özet ve öneriye dönüştürür. Canonical verification, risk, decision, human-review ve policy/reason kodları deterministic pipeline kapsamındadır ve LLM sonucu ne olursa olsun korunur.
