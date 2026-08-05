using System.Collections.Generic;
using System.Text.Json.Serialization;

namespace Kokpit.Models;

// Backend JSON sözleşmesiyle birebir (snake_case Türkçe anahtarlar).

public record Aday(
    [property: JsonPropertyName("model")] string Model,
    [property: JsonPropertyName("skor")] double Skor,
    [property: JsonPropertyName("ulke")] string? Ulke,
    [property: JsonPropertyName("rol")] string? Rol);

public record Hedef(
    [property: JsonPropertyName("id")] int Id,
    [property: JsonPropertyName("sinif")] string Sinif,
    [property: JsonPropertyName("guven")] double Guven,
    [property: JsonPropertyName("bbox")] int[] Bbox,
    [property: JsonPropertyName("hiz_px_s")] double HizPxS,
    [property: JsonPropertyName("zigzag")] double Zigzag,
    [property: JsonPropertyName("hits")] int Hits,
    [property: JsonPropertyName("model")] string? Model,
    [property: JsonPropertyName("model_skor")] double? ModelSkor,
    [property: JsonPropertyName("dusuk_guven")] bool? DusukGuven,
    [property: JsonPropertyName("ulke")] string? Ulke,
    [property: JsonPropertyName("uretici")] string? Uretici,
    [property: JsonPropertyName("rol")] string? Rol,
    [property: JsonPropertyName("adaylar")] List<Aday> Adaylar,
    [property: JsonPropertyName("vlm")] VlmSonuc? Vlm,
    [property: JsonPropertyName("llm")] LlmSonuc? Llm)
{
    // Datasette olmayan uçak → yanıltıcı model adı yerine "Bilinmeyen İHA".
    [JsonIgnore] public bool Belirsiz => DusukGuven == true;
    [JsonIgnore] public string GoruntuModel => Belirsiz ? "Bilinmeyen İHA" : (Model ?? "—");
    [JsonIgnore] public string AdaylarBaslik => Belirsiz ? "OLASI EŞLEŞMELER" : "ADAYLAR";
    [JsonIgnore] public bool VlmVar => Vlm is not null;
    [JsonIgnore] public bool LlmVar => Llm is not null;
}

public record VlmSonuc(
    [property: JsonPropertyName("dogrulama")] string? Dogrulama,
    [property: JsonPropertyName("gercek_tahmin")] string? GercekTahmin,
    [property: JsonPropertyName("arac_sinifi")] string? AracSinifi,
    [property: JsonPropertyName("tehdit_seviyesi")] string? TehditSeviyesi,
    [property: JsonPropertyName("gorsel_analiz")] string? GorselAnaliz,
    [property: JsonPropertyName("gidis_yonu")] string? GidisYonu);

public record LlmSonuc(
    [property: JsonPropertyName("summary")] string? Summary,
    [property: JsonPropertyName("risk")] string? Risk,
    [property: JsonPropertyName("actions")] List<string>? Actions);


public record HedefPaket(
    [property: JsonPropertyName("frame")] int Frame,
    [property: JsonPropertyName("hedefler")] List<Hedef> Hedefler);

public record TaniSonuc(
    [property: JsonPropertyName("model")] string? Model,
    [property: JsonPropertyName("skor")] double Skor,
    [property: JsonPropertyName("dusuk_guven")] bool DusukGuven,
    [property: JsonPropertyName("margin")] double Margin,
    [property: JsonPropertyName("ulke")] string? Ulke,
    [property: JsonPropertyName("uretici")] string? Uretici,
    [property: JsonPropertyName("rol")] string? Rol,
    [property: JsonPropertyName("adaylar")] List<Aday> Adaylar)
{
    [JsonIgnore] public bool Belirsiz => DusukGuven;
    [JsonIgnore] public string GoruntuModel => Belirsiz ? "Bilinmeyen İHA" : (Model ?? "—");
}

public record MetaDto(
    [property: JsonPropertyName("model_sayisi")] int ModelSayisi,
    [property: JsonPropertyName("ulkeler")] List<string> Ulkeler,
    [property: JsonPropertyName("roller")] List<string> Roller);

public record DurumDto(
    [property: JsonPropertyName("calisiyor")] bool Calisiyor,
    [property: JsonPropertyName("kaynak")] string Kaynak,
    [property: JsonPropertyName("frame_no")] int FrameNo,
    [property: JsonPropertyName("hedef_sayisi")] int HedefSayisi,
    [property: JsonPropertyName("model_sayisi")] int ModelSayisi);

public record KayitSatiri(
    [property: JsonPropertyName("zaman")] string Zaman,
    [property: JsonPropertyName("track_id")] int TrackId,
    [property: JsonPropertyName("sinif")] string Sinif,
    [property: JsonPropertyName("model")] string Model,
    [property: JsonPropertyName("skor")] double Skor,
    [property: JsonPropertyName("ulke")] string? Ulke,
    [property: JsonPropertyName("rol")] string? Rol);

public record GecmisDto(
    [property: JsonPropertyName("kayitlar")] List<KayitSatiri> Kayitlar);
