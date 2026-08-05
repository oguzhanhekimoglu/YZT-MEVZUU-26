using System;
using System.IO;
using System.Net.Http;
using System.Net.Http.Json;
using System.Threading.Tasks;
using Kokpit.Models;

namespace Kokpit.Services;

/// <summary>Python FastAPI backend'ine HTTP istemci.</summary>
public class BackendClient
{
    private readonly HttpClient _http;
    public string TabanUrl { get; }

    public BackendClient(string tabanUrl = "http://127.0.0.1:8000")
    {
        TabanUrl = tabanUrl.TrimEnd('/');
        _http = new HttpClient { BaseAddress = new Uri(TabanUrl), Timeout = TimeSpan.FromSeconds(30) };
    }

    public string VideoUrl => TabanUrl + "/video";
    public string HedeflerWsUrl => (TabanUrl.StartsWith("https") ? "wss" : "ws")
        + TabanUrl.Substring(TabanUrl.IndexOf(':')) + "/hedefler";

    public string ReferansUrl(string model) =>
        TabanUrl + "/referans?model=" + Uri.EscapeDataString(model);

    public async Task<bool> OturumBaslat(string videoYolu)
    {
        var r = await _http.PostAsJsonAsync("/oturum/baslat", new { video_yolu = videoYolu });
        return r.IsSuccessStatusCode;
    }

    public async Task OturumDurdur() => await _http.PostAsync("/oturum/durdur", null);

    public async Task<DurumDto?> Durum() => await _http.GetFromJsonAsync<DurumDto>("/durum");

    public async Task<MetaDto?> Meta() => await _http.GetFromJsonAsync<MetaDto>("/meta");

    public async Task<GecmisDto?> Gecmis(int adet = 100) =>
        await _http.GetFromJsonAsync<GecmisDto>($"/gecmis?adet={adet}");

    public async Task<TaniSonuc?> Tani(string dosyaYolu)
    {
        using var form = new MultipartFormDataContent();
        var bytes = await File.ReadAllBytesAsync(dosyaYolu);
        form.Add(new ByteArrayContent(bytes), "dosya", Path.GetFileName(dosyaYolu));
        var r = await _http.PostAsync("/tani", form);
        return r.IsSuccessStatusCode ? await r.Content.ReadFromJsonAsync<TaniSonuc>() : null;
    }

    /// <summary>Backend ayakta mı (durum çekilebiliyor mu)?</summary>
    public async Task<bool> Saglik()
    {
        try { return await Durum() != null; }
        catch { return false; }
    }
}
