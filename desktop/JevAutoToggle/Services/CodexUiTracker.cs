using System.Diagnostics;
using System.Runtime.InteropServices;
using System.Windows;
using System.Windows.Automation;

namespace JevCodexAutoToggle.Services;

internal sealed record CodexAnchor(IntPtr WindowHandle, int ProcessId, Rect Bounds, string Label);

internal sealed class CodexUiTracker
{
    public CodexAnchor? TryFindComposerStripAnchor()
    {
        var foreground = NativeWindowStyles.GetForegroundWindow();
        if (foreground == IntPtr.Zero)
            return null;

        try
        {
            var window = AutomationElement.FromHandle(foreground);
            if (window is null || window.Current.IsOffscreen)
                return null;

            var windowBounds = window.Current.BoundingRectangle;
            if (windowBounds.IsEmpty || windowBounds.Width < 500 || windowBounds.Height < 350)
                return null;

            // The model selector is the stable visual neighbour requested by
            // the user. It is preferred over the effort selector because the
            // effort selector can be absent until the composer is expanded.
            if (LooksLikeCodexWindow(window))
            {
                var model = PickBest(
                    window,
                    foreground,
                    windowBounds,
                    FindComposerControls(window),
                    requireModelName: true);
                if (model is not null)
                    return model;

                // No GPT-labelled control was exposed (collapsed composer,
                // signed-out picker, locale without a model-name label). Keep
                // the badge available by anchoring to the composer region.
                return BuildFallbackAnchor(foreground, window.Current.ProcessId, windowBounds);
            }

            return null;
        }
        catch (ElementNotAvailableException) { return null; }
        catch (COMException) { return null; }
        catch (InvalidOperationException) { return null; }
    }

    private static AutomationElementCollection FindComposerControls(AutomationElement window)
    {
        return window.FindAll(
            TreeScope.Descendants,
            new System.Windows.Automation.OrCondition(
                new PropertyCondition(
                    AutomationElement.ControlTypeProperty,
                    ControlType.Button),
                new PropertyCondition(
                    AutomationElement.ControlTypeProperty,
                    ControlType.ComboBox),
                new PropertyCondition(
                    AutomationElement.ControlTypeProperty,
                    ControlType.Custom)));
    }

    private static CodexAnchor? PickBest(
        AutomationElement window,
        IntPtr foreground,
        Rect windowBounds,
        AutomationElementCollection candidates,
        bool requireModelName)
    {
        CodexAnchor? best = null;
        double bestScore = double.MinValue;

        foreach (AutomationElement candidate in candidates)
        {
            try
            {
                if (candidate.Current.IsOffscreen || !candidate.Current.IsEnabled)
                    continue;

                var label = (candidate.Current.Name ?? string.Empty).Trim();
                if (string.IsNullOrWhiteSpace(label))
                    continue;

                if (requireModelName && !LooksLikeModelName(label))
                    continue;

                var bounds = candidate.Current.BoundingRectangle;
                if (bounds.IsEmpty || bounds.Width < 36 || bounds.Height < 18)
                    continue;

                // The composer controls sit in the lower-right region of the
                // foreground Codex window. This rejects menus/toolbars elsewhere.
                var lower = bounds.Top >= windowBounds.Top + windowBounds.Height * 0.55;
                var right = bounds.Left >= windowBounds.Left + windowBounds.Width * 0.40;
                if (!lower || !right)
                    continue;

                var bottomProximity = 1.0 - Math.Min(
                    1.0,
                    Math.Abs(windowBounds.Bottom - bounds.Bottom) / Math.Max(1.0, windowBounds.Height));
                var rightness = (bounds.Left - windowBounds.Left) / Math.Max(1.0, windowBounds.Width);
                var score = bottomProximity + rightness;

                if (score <= bestScore)
                    continue;

                bestScore = score;
                best = new CodexAnchor(
                    foreground,
                    window.Current.ProcessId,
                    bounds,
                    label);
            }
            catch (ElementNotAvailableException) { }
            catch (COMException) { }
        }

        return best;
    }

    private static CodexAnchor BuildFallbackAnchor(IntPtr foreground, int processId, Rect windowBounds)
    {
        // The model selector lives in the lower-right corner of the Codex
        // window. Values are physical pixels (same space as BoundingRectangle).
        const double rightMargin = 16;
        const double bottomMargin = 18;
        const double selectorWidth = 150;
        const double selectorHeight = 34;

        var left = windowBounds.Right - rightMargin - selectorWidth;
        var top = windowBounds.Bottom - bottomMargin - selectorHeight;
        return new CodexAnchor(
            foreground,
            processId,
            new Rect(left, top, selectorWidth, selectorHeight),
            "composer-fallback");
    }

    private bool LooksLikeCodexWindow(AutomationElement window)
    {
        string title;
        int processId;
        try
        {
            title = (window.Current.Name ?? string.Empty).Trim();
            processId = window.Current.ProcessId;
        }
        catch
        {
            return false;
        }

        if (title.Contains("Codex", StringComparison.OrdinalIgnoreCase))
            return true;

        // Reliable identity regardless of window title or locale: the window
        // belongs to the Codex desktop process (Electron main/renderer are all
        // named "codex", and the image ships under OpenAI\Codex).
        if (IsCodexProcess(processId))
            return true;

        // Current Chinese builds expose distinctive composer labels even when
        // the top-level packaged window title/process name is generic.
        foreach (var evidence in new[] { "帮我批准", "随心输入" })
        {
            try
            {
                var node = window.FindFirst(
                    TreeScope.Descendants,
                    new PropertyCondition(AutomationElement.NameProperty, evidence));
                if (node is not null)
                    return true;
            }
            catch (ElementNotAvailableException) { }
            catch (COMException) { }
        }

        return false;
    }

    private static bool IsCodexProcess(int processId)
    {
        try
        {
            var process = Process.GetProcessById(processId);
            if (string.Equals(process.ProcessName, "codex", StringComparison.OrdinalIgnoreCase))
                return true;

            var path = process.MainModule?.FileName;
            if (!string.IsNullOrEmpty(path)
                && path.Contains(@"\OpenAI\Codex\", StringComparison.OrdinalIgnoreCase))
                return true;
        }
        catch
        {
            // Access denied / exited / no module — fall through to other checks.
        }
        return false;
    }

    private static bool LooksLikeModelName(string label) =>
        label.StartsWith("GPT-", StringComparison.OrdinalIgnoreCase)
        || label.StartsWith("gpt-", StringComparison.OrdinalIgnoreCase);
}
