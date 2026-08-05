using System;
using System.Collections.ObjectModel;
using System.IO;
using System.Linq;
using System.Net.Http;
using System.Threading.Tasks;
using System.Windows;
using System.Windows.Media.Imaging;
using CommunityToolkit.Mvvm.ComponentModel;
using CommunityToolkit.Mvvm.Input;
using Kokpit.Models;
using Kokpit.Services;
using Microsoft.Win32;

namespace Kokpit.ViewModels;

public partial class AnaVM : ObservableObject
{
    private readonly BackendClient _api = new();
    private readonly MjpegStreamer _mjpeg = new();
    private readonly HedefSocket _soket = new();
    private readonly HttpClient _http = new();

    [ObservableProperty] private BitmapSource? _kareGoruntu;
    [ObservableProperty] private Hedef? _seciliHedef;
    [ObservableProperty] private BitmapSource? _referansGoruntu;   // seçili modelin dataset fotosu
    [ObservableProperty] private string _videoYolu = "";
    [ObservableProperty] private string _durumMetni = "Backend bekleniyor…";
    [ObservableProperty] private bool _backendHazir;
    [ObservableProperty] private bool _calisiyor;
    [ObservableProperty] private int _modelSayisi;

    // Tek-görsel test
    [ObservableProperty] private TaniSonuc? _testSonuc;
    [ObservableProperty] private BitmapSource? _testGoruntu;
    [ObservableProperty] private BitmapSource? _testReferans;

    public ObservableCollection<Hedef> Hedefler { get; } = new();
    public ObservableCollection<KayitSatiri> Gecmis { get; } = new();

    public AnaVM()
    {
        _mjpeg.KareGeldi += bmp => UI(() => KareGoruntu = bmp);
        _mjpeg.Hata += m => UI(() => DurumMetni = "Video hatası: " + m);
        _soket.PaketGeldi += p => UI(() => HedefGuncelle(p));
        _ = Baglan();
    }

    private static void UI(Action a) => Application.Current?.Dispatcher.Invoke(a);

    // Seçili hedef değişince modelin referans fotosunu yükle.
    partial void OnSeciliHedefChanged(Hedef? value) => _ = ReferansYukle(value);

    private string _lastRefModel = "";

    private async Task ReferansYukle(Hedef? h)
    {
        if (h?.Model is null || h.Belirsiz) { UI(() => { ReferansGoruntu = null; _lastRefModel = ""; }); return; }
        if (h.Model == _lastRefModel && ReferansGoruntu != null) return; // Zaten yüklü
        
        _lastRefModel = h.Model;
        var bmp = await GoruntuYukleUrl(_api.ReferansUrl(h.Model));
        UI(() => ReferansGoruntu = bmp);
    }

    private async Task<BitmapSource?> GoruntuYukleUrl(string url)
    {
        try { return BitmapYap(await _http.GetByteArrayAsync(url)); }
        catch { return null; }
    }

    private static BitmapSource BitmapYap(byte[] bytes)
    {
        var bmp = new BitmapImage();
        using var ms = new MemoryStream(bytes);
        bmp.BeginInit();
        bmp.CacheOption = BitmapCacheOption.OnLoad;
        bmp.StreamSource = ms;
        bmp.EndInit();
        bmp.Freeze();
        return bmp;
    }

    private async Task Baglan()
    {
        for (int i = 0; i < 90; i++)
        {
            if (await _api.Saglik()) { BackendHazir = true; break; }
            await Task.Delay(1000);
        }
        if (!BackendHazir) { DurumMetni = "Backend'e bağlanılamadı (:8000)."; return; }
        var meta = await _api.Meta();
        ModelSayisi = meta?.ModelSayisi ?? 0;
        DurumMetni = $"Hazır · {ModelSayisi} model indeksli";
    }

    private void HedefGuncelle(HedefPaket p)
    {
        Hedefler.Clear();
        foreach (var h in p.Hedefler) Hedefler.Add(h);
        
        // OTOMATİK SEÇİM: Skoru en yüksek olanı veya ilkini seç
        var best = Hedefler.OrderByDescending(x => x.ModelSkor ?? 0).FirstOrDefault() ?? Hedefler.FirstOrDefault();
        
        if (best != null)
        {
            // Modeli değişmediyse referans resmi tekrar indirmeyi önlemek için (Titreme koruması)
            if (SeciliHedef != null && SeciliHedef.Id == best.Id && SeciliHedef.Model == best.Model)
            {
                // Sadece UI güncellenmesi için atama yap, ReferansYukle içinde engellenecek (altta ekledim)
            }
            SeciliHedef = best;
        }
        else
        {
            SeciliHedef = null;
        }
    }

    [RelayCommand]
    private void VideoAc()
    {
        var kok = @"C:\Users\oguz\Desktop\uav-final";
        var d = new OpenFileDialog
        {
            Filter = "Video|*.mp4;*.avi;*.mov;*.mkv;*.webm|Tümü|*.*",
            InitialDirectory = System.IO.Directory.Exists(kok) ? kok : "",
        };
        if (d.ShowDialog() == true) VideoYolu = d.FileName;
    }

    [RelayCommand]
    private async Task Baslat()
    {
        if (!BackendHazir) { DurumMetni = "Backend hazır değil."; return; }
        if (string.IsNullOrWhiteSpace(VideoYolu)) { DurumMetni = "Önce video seç."; return; }
        _mjpeg.Durdur();
        _soket.Durdur();
        Hedefler.Clear();
        SeciliHedef = null;
        KareGoruntu = null;
        if (!await _api.OturumBaslat(VideoYolu))
        {
            DurumMetni = "Oturum başlatılamadı (yol/erişim sorunu).";
            return;
        }
        Calisiyor = true;
        DurumMetni = "İşleniyor…";
        await Task.Delay(400);
        _mjpeg.Basla(_api.VideoUrl);
        _soket.Basla(_api.HedeflerWsUrl);
        _ = KodekKontrol();
    }

    private async Task KodekKontrol()
    {
        await Task.Delay(2500);
        var d = await _api.Durum();
        if (d != null && !d.Calisiyor && d.FrameNo == 0)
            UI(() => DurumMetni = "⚠ Video açılamadı — format/codec desteklenmiyor olabilir (mp4/H.264 dene).");
    }

    [RelayCommand]
    private async Task Durdur()
    {
        await _api.OturumDurdur();
        _mjpeg.Durdur();
        _soket.Durdur();
        Calisiyor = false;
        DurumMetni = "Durduruldu.";
    }

    [RelayCommand]
    private async Task GecmisYenile()
    {
        var g = await _api.Gecmis(100);
        Gecmis.Clear();
        foreach (var k in g?.Kayitlar ?? Enumerable.Empty<KayitSatiri>().ToList())
            Gecmis.Add(k);
    }

    // --- Tek-görsel test (video olmadan foto → model) ---
    [RelayCommand]
    private async Task FotoTest()
    {
        if (!BackendHazir) { DurumMetni = "Backend hazır değil."; return; }
        var d = new OpenFileDialog { Filter = "Görsel|*.jpg;*.jpeg;*.png|Tümü|*.*" };
        if (d.ShowDialog() != true) return;
        DurumMetni = "Test görseli tanınıyor…";
        var sonuc = await _api.Tani(d.FileName);
        var img = BitmapYap(await File.ReadAllBytesAsync(d.FileName));
        BitmapSource? refG = null;
        if (sonuc?.Model is not null && !sonuc.DusukGuven)
            refG = await GoruntuYukleUrl(_api.ReferansUrl(sonuc.Model));
        UI(() =>
        {
            TestGoruntu = img;
            TestSonuc = sonuc;
            TestReferans = refG;
            DurumMetni = sonuc?.Model is not null ? $"Test → {sonuc.GoruntuModel}" : "Test: sonuç yok";
        });
    }

    [RelayCommand]
    private void TestKapat()
    {
        TestSonuc = null;
        TestGoruntu = null;
        TestReferans = null;
    }
}
