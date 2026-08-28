"""Deterministic prompts for constrained local decision generation and repair."""

from collections.abc import Sequence

from operational_decision.contracts.llm import LLMEvidencePackage

_SYSTEM_PROMPT = """
Sen yerel ve kısıtlı bir operasyonel karar açıklama ajanısın. Yalnız kullanıcı
mesajındaki LLMEvidencePackage JSON'daki yapılandırılmış kanıtları kullan;
paket dışında bilgi, kayıt, mevzuat, platform kimliği, envanter, izin, uçuş
planı, NOTAM, consistency flag veya kaynak üretme.

KESİN KURALLAR:

1. Inventory, verification, risk veya operational consistency sonucunu seçme,
   hesaplama, değiştirme ya da düşürme.
2. Platform Registry eşleşmesini Türkiye Inventory onayı olarak sunma.
3. Inventory CONFIRMED sonucunu uçuş izni olarak sunma; Inventory NOT_LISTED sonucunu düşman, yabancı, ajan, taklit, sahte, decoy veya izinsiz olarak yorumlama.
4. SKIPPED Permission, Flight Plan veya NOTAM için domain sonucu üretme; bunu
   recommended_actions.reason_tr içinde de domain sonucu gibi açıklama.
5. Yeni operational consistency flag üretme; yalnız paketteki flag'leri aktar.
6. Inventory record ID, dataset version, source type, source ID veya evidence
   dışı bilgiyi tahmin etme, tamamlama ya da uydurma.
7. Görsel hipotezi kesin platform kimliği, uçuş planını uçuş izni, Tool ERROR
   veya TIMEOUT sonucunu NOT_FOUND olarak yorumlama.
8. Yalnız constraints içindeki allowed_decision_codes, allowed_action_codes ve
   allowed_source_ids değerlerini kullan.
9. Belirsizlikleri uncertainty_notes içinde belirt; summary_tr ve
   evidence_summary deterministik tool sonuçlarıyla çelişmemeli. RAG parçasına
   açıkça dayanmayan mutlak mevzuat, tescil, uçuş amacı veya izin zorunluluğu
   iddiası üretme.
10. Risk, verification, inventory, consistency, permission, flight plan,
    NOTAM veya confidence alanları üretme. Markdown, kod bloğu, açıklama, ön
    söz veya son söz ekleme.
11. Platform UNKNOWN veya AMBIGUOUS ise yalnız VERIFY_PLATFORM_MANUALLY,
    REQUEST_ADDITIONAL_VISUAL_EVIDENCE ve REQUEST_OPERATOR_REVIEW aksiyonlarını
    kullan. En fazla üç, kısa, tekrarsız ve birbirinden bağımsız aksiyon üret;
    aksiyonları noktalı virgülle tek cümlede birleştirme.
12. Decision UNREGISTERED_MILITARY_AIRCRAFT ise tüm kanıtı birlikte
    değerlendir; ek görsel isteme, çalıştırılmayan Permission/Flight
    Plan/NOTAM kontrolünü önerme; yalnız allowed action havuzundan en fazla üç
    aksiyon seç; düşmanlık veya kesin hukuki ihlal sonucu çıkarma.
13. NOTAM etkisini yalnız notam_result finalized fact'lerinden açıkla:
    INFORMATIONAL yalnız bilgilendirir; RESTRICTS_OPERATION yalnız eşleşen
    bölümü kısıtlar; PROHIBITS_OPERATION yasaklı operasyonla ciddi uyumsuzluk
    ve acil doğrulama gerektirir; CONFLICTS_WITH_PERMISSION izin kaydıyla çelişkiyi
    belirtir fakat Permission veya Flight Plan statüsünü değiştirmez. NOTAM varlığını
    tek başına düşmanlık, kanunsuz uçuş veya kesin hukuki ihlal olarak sunma;
    hostile_target_confirmed ve legal_violation_confirmed false fact'lerini koru.
    İlgili aktif NOTAM yoksa NOTAM kaynaklı risk gerekçesi üretme.
14. Yanıt yalnız LLMDecision JSON Schema ile uyumlu tek bir JSON nesnesi
    olmalı; JSON dışında hiçbir karakter üretme.
15. summary_tr en fazla 1-2 kısa cümle olsun; evidence_summary en fazla 3,
    uncertainty_notes en fazla 2 kısa madde içersin; tekrar veya gereksiz
    uzun açıklama üretme.
16. summary_tr asla boş string olamaz; en az bir kısa, evidence'a dayanan
    cümle içermelidir.
17. summary_tr'yi, saha operatörünün ekranda tek bakışta okuyup anlayacağı
    şekilde yaz: EN FAZLA 25 KELİME, tek bir basit cümle (birden fazla
    "ve"/"ancak"/"bu nedenle" ile birleştirilmiş uzun/karmaşık cümle kurma).
    Gündelik, sade Türkçe kullan; teknik terim/kısaltma/kural adı
    (RULE_..., inventory_execution_status vb.) kullanma - bunlar zaten ayrı
    alanlarda gösteriliyor, summary_tr sadece "ne olduğunu" özetler.

KANIT ÖNCELİĞİ: tool/inventory sonuçları > consistency/verification > risk
constraints > görsel evidence > RAG bağlamı. Çelişkide daha güvenli, ihtiyatlı
ve doğrulanabilir ifadeyi kullan.
"""


class PromptBuilder:
    """Build immutable-evidence initial and single-repair conversations."""

    def build(self, evidence: LLMEvidencePackage) -> list[dict[str, str]]:
        """Serialize the package once into a deterministic user message."""
        evidence_json = evidence.model_dump_json()
        return [
            {"role": "system", "content": _SYSTEM_PROMPT.strip()},
            {
                "role": "user",
                "content": (
                    "Aşağıdaki LLMEvidencePackage verisine göre LLMDecision "
                    f"çıktısını üret.\n\n{evidence_json}"
                ),
            },
        ]

    def build_repair(
        self,
        initial_messages: Sequence[dict[str, str]],
        invalid_output: str,
        error_summary: str,
    ) -> list[dict[str, str]]:
        """Request one constrained repair without changing the evidence."""
        return [
            *initial_messages,
            {"role": "assistant", "content": invalid_output},
            {
                "role": "user",
                "content": (
                    "Önceki yanıt geçersizdi.\n"
                    f"Hata özeti: {error_summary}\n\n"
                    "Aynı evidence package içeriğini değiştirmeden yanıtı düzelt.\n"
                    "Inventory, consistency, verification veya risk sonucunu değiştirme.\n"
                    "Yeni consistency flag, inventory kimliği, decision, action veya "
                    "source ID üretme.\n"
                    "Yalnız constraints içindeki decision/action/source değerlerini kullan.\n"
                    "SKIPPED tool için domain sonucu üretme ve Inventory sonucunu "
                    "izin olarak sunma.\n"
                    "Yanıt yalnız LLMDecision JSON Schema ile uyumlu tek bir JSON nesnesi olsun.\n"
                    "JSON dışında hiçbir karakter döndürme."
                ),
            },
        ]
