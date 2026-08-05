using System.Windows;
using System.Windows.Input;
using Kokpit.ViewModels;

namespace Kokpit;

public partial class MainWindow : Window
{
    public MainWindow()
    {
        InitializeComponent();
        DataContext = new AnaVM();
    }

    // F11: kenarlıksız gerçek tam ekran ↔ normal; Esc: tam ekrandan çık.
    private void Pencere_KeyDown(object sender, KeyEventArgs e)
    {
        if (e.Key == Key.F11)
        {
            bool tam = WindowStyle == WindowStyle.None;
            WindowStyle = tam ? WindowStyle.SingleBorderWindow : WindowStyle.None;
            WindowState = WindowState.Normal;   // yeniden maximize tetiklemek için
            WindowState = WindowState.Maximized;
        }
        else if (e.Key == Key.Escape && WindowStyle == WindowStyle.None)
        {
            WindowStyle = WindowStyle.SingleBorderWindow;
            WindowState = WindowState.Maximized;
        }
    }
}
