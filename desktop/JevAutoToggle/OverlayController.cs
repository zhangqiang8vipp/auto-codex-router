using System.Windows.Threading;
using JevCodexAutoToggle.Services;

namespace JevCodexAutoToggle;

internal sealed class OverlayController : IDisposable
{
    private readonly Dispatcher _dispatcher;
    private readonly OverlayWindow _overlay = new();
    private readonly CodexUiTracker _tracker = new();
    private readonly RouterControlClient _router = new();
    private readonly OverlayDiagnostics _diagnostics = new();
    private readonly DispatcherTimer _uiTimer;
    private readonly DispatcherTimer _statusTimer;
    private readonly CancellationTokenSource _cts = new();

    private AutoSnapshot _snapshot = new(false, false, "Connecting to Jev Router…", null, null);
    private bool _busy;
    private bool _statusInFlight;
    private bool _hasComposerAnchor;
    private string? _lastAnchorLabel;
    public OverlayController(Dispatcher dispatcher)
    {
        _dispatcher = dispatcher;
        _overlay.ToggleRequested += OnToggleRequested;
        _overlay.SetState(_snapshot, busy: false);

        _uiTimer = new DispatcherTimer(
            TimeSpan.FromMilliseconds(400),
            DispatcherPriority.Background,
            (_, _) => {
                RefreshAnchor();
                // Re-assert topmost so the badge never falls behind the
                // Codex WebView surface between anchor refreshes.
                if (_overlay.IsVisible) _overlay.Topmost = true;
            },
            dispatcher);

        _statusTimer = new DispatcherTimer(
            TimeSpan.FromSeconds(1),
            DispatcherPriority.Background,
            async (_, _) => await RefreshStatusAsync(),
            dispatcher);
    }

    public void Start()
    {
        _overlay.SetFixedPosition();
        _overlay.Hide();
        _uiTimer.Start();
        _statusTimer.Start();
        _ = RefreshStatusAsync();
    }

    private void RefreshAnchor()
    {
        CodexAnchor? anchor;
        try
        {
            anchor = _tracker.TryFindComposerStripAnchor();
        }
        catch
        {
            anchor = null;
        }

        if (anchor is null)
        {
            // Codex is not in the foreground — hide the badge so it never
            // floats over other apps.
            if (_overlay.IsVisible) _overlay.Hide();
            _hasComposerAnchor = false;
            _diagnostics.Write(false, _lastAnchorLabel, _snapshot,
                "codex not in foreground; hiding overlay");
            return;
        }

        _hasComposerAnchor = true;
        _lastAnchorLabel = anchor.Label;
        _overlay.SetAnchor(anchor);
        if (!_overlay.IsVisible) _overlay.Show();
        _overlay.Topmost = true;
        _diagnostics.Write(true, _lastAnchorLabel, _snapshot);
    }

    private async Task RefreshStatusAsync()
    {
        if (_busy || _statusInFlight || _cts.IsCancellationRequested) return;
        _statusInFlight = true;
        try
        {
            _snapshot = await _router.GetStatusAsync(_cts.Token);
        }
        catch (OperationCanceledException)
        {
            return;
        }
        catch (Exception ex)
        {
            _snapshot = new AutoSnapshot(false, false, ex.GetType().Name, null, null);
        }
        finally
        {
            _statusInFlight = false;
        }

        _overlay.SetState(_snapshot, _busy);
        _diagnostics.Write(_hasComposerAnchor, _lastAnchorLabel, _snapshot);
    }

    private static readonly string ClickLog = System.IO.Path.Combine(
        System.Environment.GetFolderPath(System.Environment.SpecialFolder.UserProfile),
        ".codex", "codex-router", "jev-auto-toggle.click.log");

    private static void Log(string msg)
    {
        try { System.IO.File.AppendAllText(ClickLog, $"[{DateTime.Now:HH:mm:ss.fff}] {msg}\n"); }
        catch { }
    }

    private async void OnToggleRequested(object? sender, EventArgs e)
    {
        Log($"OnToggleRequested enter: busy={_busy} avail={_snapshot.Available} auto={_snapshot.Auto}");
        if (_busy || !_snapshot.Available)
        {
            Log("bail: busy or not available");
            return;
        }
        _busy = true;
        _overlay.SetState(_snapshot, busy: true);

        try
        {
            var target = !_snapshot.Auto;
            Log($"calling SetAutoAsync({target})");
            _snapshot = await _router.SetAutoAsync(target, _cts.Token);
            Log($"result: auto={_snapshot.Auto} avail={_snapshot.Available} err={_snapshot.Error}");
        }
        catch (OperationCanceledException)
        {
            Log("cancelled");
            return;
        }
        catch (Exception ex)
        {
            Log($"EXCEPTION {ex.GetType().Name}: {ex.Message}");
            _snapshot = new AutoSnapshot(
                _snapshot.Auto,
                false,
                $"{ex.GetType().Name}: {ex.Message}",
                _snapshot.RedirectModel,
                _snapshot.Route);
        }
        finally
        {
            _busy = false;
            _overlay.SetState(_snapshot, busy: false);
        }
    }

    public void Dispose()
    {
        _cts.Cancel();
        _uiTimer.Stop();
        _statusTimer.Stop();
        _overlay.Close();
        _router.Dispose();
        _cts.Dispose();
    }
}
