using System;
using System.Net.WebSockets;
using System.Text;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using Kokpit.Models;

namespace Kokpit.Services;

/// <summary>Backend'in /hedefler WebSocket'ine bağlanır; her hedef paketini yayınlar.</summary>
public class HedefSocket
{
    public event Action<HedefPaket>? PaketGeldi;
    public event Action<string>? Hata;
    private CancellationTokenSource? _cts;

    public void Basla(string wsUrl)
    {
        Durdur();
        _cts = new CancellationTokenSource();
        _ = Task.Run(() => Dongu(wsUrl, _cts.Token));
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
            using var ws = new ClientWebSocket();
            await ws.ConnectAsync(new Uri(url), ct);
            var buf = new byte[1 << 20];
            while (!ct.IsCancellationRequested && ws.State == WebSocketState.Open)
            {
                var sb = new StringBuilder();
                WebSocketReceiveResult res;
                do
                {
                    res = await ws.ReceiveAsync(new ArraySegment<byte>(buf), ct);
                    if (res.MessageType == WebSocketMessageType.Close) return;
                    sb.Append(Encoding.UTF8.GetString(buf, 0, res.Count));
                } while (!res.EndOfMessage);

                try
                {
                    var paket = JsonSerializer.Deserialize<HedefPaket>(sb.ToString());
                    if (paket != null) PaketGeldi?.Invoke(paket);
                }
                catch (JsonException) { /* bozuk paket atla */ }
            }
        }
        catch (OperationCanceledException) { }
        catch (Exception e) { Hata?.Invoke(e.Message); }
    }
}
