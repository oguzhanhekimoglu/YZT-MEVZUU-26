using System;
using System.Globalization;
using System.Windows;
using System.Windows.Data;

namespace Kokpit;

/// <summary>bool'u tersler (Başlat butonu: çalışmıyorken aktif).</summary>
public class TersBool : IValueConverter
{
    public object Convert(object? v, Type t, object? p, CultureInfo c) => !(v is bool b && b);
    public object ConvertBack(object? v, Type t, object? p, CultureInfo c) => !(v is bool b && b);
}

/// <summary>null ise Collapsed, doluysa Visible (seçili model kartı).</summary>
public class NullGizle : IValueConverter
{
    public object Convert(object? v, Type t, object? p, CultureInfo c) =>
        v is null ? Visibility.Collapsed : Visibility.Visible;
    public object ConvertBack(object? v, Type t, object? p, CultureInfo c) =>
        throw new NotSupportedException();
}

/// <summary>true (düşük güven) ise uyarı rengini gösterir.</summary>
public class DusukGuvenGorunur : IValueConverter
{
    public object Convert(object? v, Type t, object? p, CultureInfo c) =>
        (v is bool b && b) ? Visibility.Visible : Visibility.Collapsed;
    public object ConvertBack(object? v, Type t, object? p, CultureInfo c) =>
        throw new NotSupportedException();
}

/// <summary>Skor (0-1) → güven çubuğu genişliği (px). Parametre = max genişlik.</summary>
public class OranGenislik : IValueConverter
{
    public object Convert(object? v, Type t, object? p, CultureInfo c)
    {
        double skor = v is double d ? d : 0;
        double max = p is not null && double.TryParse(p.ToString(), NumberStyles.Any,
            CultureInfo.InvariantCulture, out var m) ? m : 140;
        return Math.Max(2, Math.Min(1, skor) * max);
    }
    public object ConvertBack(object? v, Type t, object? p, CultureInfo c) =>
        throw new NotSupportedException();
}
