using System.Windows;
using System.Windows.Controls;
using System.Windows.Interop;
using System.Windows.Media;
using JevCodexAutoToggle.Services;

namespace JevCodexAutoToggle;

public partial class OverlayWindow : Window
{
    private IntPtr _targetWindowHandle;

    public event EventHandler? ToggleRequested;

    public OverlayWindow()
    {
        InitializeComponent();
    }

    protected override void OnSourceInitialized(EventArgs e)
    {
        base.OnSourceInitialized(e);
        var handle = new WindowInteropHelper(this).Handle;
        var style = NativeWindowStyles.GetWindowLongPtr(handle, NativeWindowStyles.GwlExStyle).ToInt64();
        // Keep tool-window styling (no taskbar, no alt-tab entry) but drop
        // WS_EX_NOACTIVATE: it can swallow mouse-button messages on layered
        // WPF windows, making the badge look dead even though the timer keeps
        // refreshing.
        style |= NativeWindowStyles.WsExToolWindow;
        style &= ~NativeWindowStyles.WsExNoActivate;
        _ = NativeWindowStyles.SetWindowLongPtr(
            handle,
            NativeWindowStyles.GwlExStyle,
            new IntPtr(style));
        // Re-assert topmost every time the window is shown so the badge never
        // gets buried under the Codex WebView surface.
        Topmost = true;
    }

    internal void SetAnchor(CodexAnchor anchor)
    {
        _targetWindowHandle = anchor.WindowHandle;
        var dpi = _targetWindowHandle != IntPtr.Zero
            ? NativeWindowStyles.GetDpiForWindow(_targetWindowHandle)
            : 96u;
        if (dpi == 0) dpi = 96;
        var scale = dpi / 96.0;

        var anchorLeft = anchor.Bounds.Left / scale;
        var anchorTop = anchor.Bounds.Top / scale;
        var anchorHeight = anchor.Bounds.Height / scale;

        // Codex places its compact/compaction circle immediately to the left
        // of the model selector. Reserve that control's visual width and put
        // Auto to its left, so this remains correct when the selected model
        // name changes.
        const double compactionControlWidth = 44;
        Left = anchorLeft - compactionControlWidth - Width - 5;
        Top = anchorTop + (anchorHeight - Height) / 2.0;
    }

    internal void SetFixedPosition()
    {
        // Keep Auto available even when Codex's WebView does not expose its
        // composer controls through UI Automation. WorkArea already excludes
        // the taskbar, so the pill stays visible without covering it.
        var workArea = SystemParameters.WorkArea;
        const double margin = 24;
        Left = workArea.Right - Width - margin;
        Top = workArea.Bottom - Height - margin;
    }

    internal void SetState(AutoSnapshot snapshot, bool busy)
    {
        AutoButton.IsEnabled = !busy && snapshot.Available;
        AutoButton.Opacity = busy ? 0.68 : 1.0;

        if (!snapshot.Available || !string.IsNullOrWhiteSpace(snapshot.Error))
        {
            SetResource("Icon", TextBlock.ForegroundProperty, "ErrorText");
            AutoButton.ToolTip = snapshot.Error ?? "Jev Auto control unavailable.";
            return;
        }

        if (snapshot.Auto)
        {
            SetResource("Icon", TextBlock.ForegroundProperty, "OnText");

            var route = snapshot.Route;
            AutoButton.ToolTip = route is { Model: not null }
                ? $"Auto ON\nLast route: {ShortModel(route.Model)} · {route.Effort ?? "default"}"
                : "Auto ON\nJev decides model + reasoning effort for each call.";
        }
        else
        {
            SetResource("Icon", TextBlock.ForegroundProperty, "OffText");
            AutoButton.ToolTip = string.IsNullOrWhiteSpace(snapshot.RedirectModel)
                ? "Auto OFF\nCodex native model + reasoning controls are active."
                : $"Auto OFF\nRestored Codex Router redirect: {snapshot.RedirectModel}";
        }
    }

    private static string ShortModel(string model) =>
        model switch
        {
            "gpt-5.6-luna" => "Luna",
            "gpt-5.6-terra" => "Terra",
            "gpt-5.6-sol" => "Sol",
            "gpt-6-astra" => "Astra",
            _ => model
        };

    private void SetResource(string name, DependencyProperty property, string resource)
    {
        AutoButton.ApplyTemplate();
        if (AutoButton.Template.FindName(name, AutoButton) is not DependencyObject target) return;
        target.SetValue(property, FindResource(resource) as Brush);
    }

    private void AutoButton_OnClick(object sender, RoutedEventArgs e)
    {
        try
        {
            var logPath = System.IO.Path.Combine(
                System.Environment.GetFolderPath(System.Environment.SpecialFolder.UserProfile),
                ".codex", "codex-router", "jev-auto-toggle.click.log");
            System.IO.File.AppendAllText(logPath,
                $"[{DateTime.Now:HH:mm:ss.fff}] click received\n");
        }
        catch { }
        ToggleRequested?.Invoke(this, EventArgs.Empty);
    }
}
