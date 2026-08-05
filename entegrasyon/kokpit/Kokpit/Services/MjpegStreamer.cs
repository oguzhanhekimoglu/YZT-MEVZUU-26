using System;
using System.IO;
using System.Net.Http;
using System.Threading;
using System.Threading.Tasks;
using System.Windows.Media.Imaging;

namespace Kokpit.Services;

/// <summary>Backend'in MJPEG akışını (multipart/x-mixed-replace) çözer; her kareyi
/// dondurulmuş BitmapSource olarak yayınlar (thread'ler arası güvenli).</summary>
public class MjpegStreamer
{
    public event Action<BitmapSource>? KareGeldi;
    public event Action<string>? Hata;
    private CancellationTokenSource? _cts;

    public void Basla(string url)
    {
        Durdur();
        _cts = new CancellationTokenSource();
        _ = Task.Run(() => Dongu(url, _cts.Token));
    }

    public void Durdur()
    {
        _cts?.Cancel();
        _cts = null;
    }

    private async Task Dongu(string url, CancellationToken ct)
    {
        try
        {
            using var http = new HttpClient { Timeout = Timeout.InfiniteTimeSpan };
            await using var stream = await http.GetStreamAsync(url, ct);
            var buf = new byte[65536];
            using var acc = new MemoryStream();
            while (!ct.IsCancellationRequested)
            {
                int n = await stream.ReadAsync(buf.AsMemory(0, buf.Length), ct);
                if (n <= 0) break;
                acc.Write(buf, 0, n);
                CikarKareler(acc);
            }
        }
        catch (OperationCanceledException) { }
        catch (Exception e) { Hata?.Invoke(e.Message); }
    }

    // Biriken tampondan tüm tam JPEG'leri (FFD8..FFD9) ayıkla; kalanı sakla.
    private void CikarKareler(MemoryStream acc)
    {
        byte[] data = acc.GetBuffer();
        int len = (int)acc.Length;
        int son = 0, i = 0;
        while (true)
        {
            int basla = Bul(data, i, len, 0xFF, 0xD8);
            if (basla < 0) break;
            int bit = Bul(data, basla + 2, len, 0xFF, 0xD9);
            if (bit < 0) break;
            int jpgSon = bit + 2;
            var jpg = new byte[jpgSon - basla];
            Array.Copy(data, basla, jpg, 0, jpg.Length);
            Coz(jpg);
            son = jpgSon;
            i = jpgSon;
        }
        if (son > 0)
        {
            int kalan = len - son;
            var yeni = new byte[kalan];
            Array.Copy(data, son, yeni, 0, kalan);
            acc.SetLength(0);
            acc.Write(yeni, 0, kalan);
        }
    }

    private static int Bul(byte[] d, int start, int len, byte a, byte b)
    {
        for (int i = Math.Max(0, start); i < len - 1; i++)
            if (d[i] == a && d[i + 1] == b) return i;
        return -1;
    }

    private void Coz(byte[] jpg)
    {
        try
        {
            var bmp = new BitmapImage();
            using var ms = new MemoryStream(jpg);
            bmp.BeginInit();
            bmp.CacheOption = BitmapCacheOption.OnLoad;
            bmp.StreamSource = ms;
            bmp.EndInit();
            bmp.Freeze();
            KareGeldi?.Invoke(bmp);
        }
        catch { /* bozuk/yarım kare atla */ }
    }
}
