//! Bifang Design System Tokens for TUI
//! Shared with desktop/web for consistent visual identity

use ratatui::style::{Color, Style};
use ratatui::text::Line;

/// Bifang Brand Colors (true-color 24-bit)
pub mod colors {
    use super::*;

    // Brand
    pub const BRAND_RED: Color = Color::Rgb(0xE6, 0x39, 0x46);
    pub const BRAND_ORANGE: Color = Color::Rgb(0xFF, 0x8A, 0x3D);
    pub const BRAND_WHITE: Color = Color::Rgb(0xF7, 0xF7, 0xF7);

    // Surfaces (Deep Slate)
    pub const SLATE_CANVAS: Color = Color::Rgb(0x0F, 0x17, 0x2A);
    pub const SLATE_ELEVATED: Color = Color::Rgb(0x1A, 0x23, 0x38);
    pub const SLATE_ELEVATED_HOVER: Color = Color::Rgb(0x20, 0x2B, 0x40);
    pub const SLATE_PANEL: Color = Color::Rgb(0x15, 0x1D, 0x30);
    pub const SLATE_PANEL_HOVER: Color = Color::Rgb(0x1C, 0x26, 0x42);
    pub const SLATE_BORDER: Color = Color::Rgb(0x2D, 0x3A, 0x50);
    pub const SLATE_BORDER_BRIGHT: Color = Color::Rgb(0x3D, 0x4A, 0x68);

    // Text
    pub const TEXT_PRIMARY: Color = Color::Rgb(0xF7, 0xF7, 0xF7);
    pub const TEXT_SECONDARY: Color = Color::Rgb(0xB8, 0xC3, 0xD6);
    pub const TEXT_MUTED: Color = Color::Rgb(0x9A, 0xA9, 0xBF);
    pub const TEXT_DISABLED: Color = Color::Rgb(0x6B, 0x7A, 0x94);
    pub const TEXT_INVERSE: Color = Color::Rgb(0x0F, 0x17, 0x2A);

    // Semantic
    pub const SUCCESS: Color = Color::Rgb(0x22, 0xC5, 0x5E);
    pub const SUCCESS_LIGHT: Color = Color::Rgb(0x4A, 0xDE, 0x80);
    pub const SUCCESS_DARK: Color = Color::Rgb(0x16, 0xA3, 0x4A);
    pub const WARNING: Color = Color::Rgb(0xF5, 0x9E, 0x0B);
    pub const WARNING_LIGHT: Color = Color::Rgb(0xFB, 0xBF, 0x24);
    pub const ERROR: Color = Color::Rgb(0xEF, 0x44, 0x44);
    pub const ERROR_LIGHT: Color = Color::Rgb(0xF8, 0x71, 0x71);
    pub const INFO: Color = Color::Rgb(0x3B, 0x82, 0xF6);
    pub const INFO_LIGHT: Color = Color::Rgb(0x60, 0xA5, 0xFA);

    // Focus
    pub const FOCUS_RING: Color = Color::Rgb(0xFF, 0x8A, 0x3D);

    /// Ember gradient stops for text gradients
    pub const EMBER_GRADIENT: [Color; 3] = [
        Color::Rgb(0xE6, 0x39, 0x46), // Red
        Color::Rgb(0xF0, 0x5A, 0x3E), // Mid
        Color::Rgb(0xFF, 0x8A, 0x3D), // Orange
    ];
}

/// Typography - Font families (for reference, TUI uses terminal fonts)
pub mod typography {
    pub const DISPLAY_FAMILY: &str = "Space Grotesk";
    pub const SANS_FAMILY: &str = "Inter";
    pub const MONO_FAMILY: &str = "JetBrains Mono";

    // Font sizes (for reference)
    pub const SIZE_XS: u16 = 11;
    pub const SIZE_SM: u16 = 12;
    pub const SIZE_BASE: u16 = 13;
    pub const SIZE_LG: u16 = 14;
    pub const SIZE_XL: u16 = 16;
    pub const SIZE_2XL: u16 = 20;
    pub const SIZE_3XL: u16 = 25;
    pub const SIZE_4XL: u16 = 32;
}

/// Spacing scale (8pt grid)
pub mod spacing {
    pub const SPACE_0: u16 = 0;
    pub const SPACE_1: u16 = 2;
    pub const SPACE_2: u16 = 4;
    pub const SPACE_3: u16 = 6;
    pub const SPACE_4: u16 = 8;
    pub const SPACE_5: u16 = 10;
    pub const SPACE_6: u16 = 12;
    pub const SPACE_8: u16 = 16;
    pub const SPACE_10: u16 = 20;
    pub const SPACE_12: u16 = 24;
    pub const SPACE_16: u16 = 32;
    pub const SPACE_20: u16 = 40;
    pub const SPACE_24: u16 = 48;
}

/// Border radius (simulated in TUI with box drawing)
pub mod border {
    pub const NONE: &str = " ";
    pub const SM: &str = "╭─╮│╰╯";  // Rounded
    pub const DEFAULT: &str = "┌─┐│└┘";   // Square
    pub const LG: &str = "╔═╗║╚╝";    // Heavy
}

/// Common Styles
pub mod styles {
    use super::*;
    use ratatui::style::{Modifier, Style};

    // Base styles
    pub fn base() -> Style {
        Style::default().fg(colors::TEXT_PRIMARY).bg(colors::SLATE_CANVAS)
    }

    pub fn panel() -> Style {
        Style::default().fg(colors::TEXT_PRIMARY).bg(colors::SLATE_PANEL)
    }

    pub fn panel_elevated() -> Style {
        Style::default().fg(colors::TEXT_PRIMARY).bg(colors::SLATE_ELEVATED)
    }

    pub fn surface() -> Style {
        Style::default().fg(colors::TEXT_SECONDARY).bg(colors::SLATE_ELEVATED)
    }

    // Text styles
    pub fn text_primary() -> Style {
        Style::default().fg(colors::TEXT_PRIMARY)
    }

    pub fn text_secondary() -> Style {
        Style::default().fg(colors::TEXT_SECONDARY)
    }

    pub fn text_muted() -> Style {
        Style::default().fg(colors::TEXT_MUTED)
    }

    pub fn text_disabled() -> Style {
        Style::default().fg(colors::TEXT_DISABLED)
    }

    // Semantic text
    pub fn text_success() -> Style {
        Style::default().fg(colors::SUCCESS)
    }

    pub fn text_warning() -> Style {
        Style::default().fg(colors::WARNING)
    }

    pub fn text_error() -> Style {
        Style::default().fg(colors::ERROR)
    }

    pub fn text_info() -> Style {
        Style::default().fg(colors::INFO)
    }

    // Ember gradient text (approximated)
    pub fn text_ember() -> Style {
        Style::default().fg(colors::BRAND_ORANGE).add_modifier(Modifier::BOLD)
    }

    pub fn text_ember_strong() -> Style {
        Style::default().fg(colors::BRAND_RED).add_modifier(Modifier::BOLD)
    }

    // Borders
    pub fn border_default() -> Style {
        Style::default().fg(colors::SLATE_BORDER)
    }

    pub fn border_bright() -> Style {
        Style::default().fg(colors::SLATE_BORDER_BRIGHT)
    }

    pub fn border_focus() -> Style {
        Style::default().fg(colors::FOCUS_RING)
    }

    pub fn border_success() -> Style {
        Style::default().fg(colors::SUCCESS)
    }

    pub fn border_error() -> Style {
        Style::default().fg(colors::ERROR)
    }

    // Buttons
    pub fn btn_primary() -> Style {
        Style::default()
            .fg(colors::BRAND_WHITE)
            .bg(colors::BRAND_RED)
            .add_modifier(Modifier::BOLD)
    }

    pub fn btn_primary_hover() -> Style {
        Style::default()
            .fg(colors::BRAND_WHITE)
            .bg(Color::Rgb(0xCC, 0x29, 0x3B))
            .add_modifier(Modifier::BOLD)
    }

    pub fn btn_secondary() -> Style {
        Style::default()
            .fg(colors::TEXT_PRIMARY)
            .bg(colors::SLATE_PANEL)
    }

    pub fn btn_secondary_hover() -> Style {
        Style::default()
            .fg(colors::TEXT_PRIMARY)
            .bg(colors::SLATE_PANEL_HOVER)
    }

    pub fn btn_ghost() -> Style {
        Style::default().fg(colors::TEXT_SECONDARY)
    }

    pub fn btn_destructive() -> Style {
        Style::default()
            .fg(colors::BRAND_WHITE)
            .bg(colors::ERROR)
            .add_modifier(Modifier::BOLD)
    }

    pub fn btn_success() -> Style {
        Style::default()
            .fg(colors::TEXT_INVERSE)
            .bg(colors::SUCCESS)
            .add_modifier(Modifier::BOLD)
    }

    // Input
    pub fn input() -> Style {
        Style::default()
            .fg(colors::TEXT_PRIMARY)
            .bg(colors::SLATE_PANEL)
    }

    pub fn input_focus() -> Style {
        Style::default()
            .fg(colors::TEXT_PRIMARY)
            .bg(colors::SLATE_PANEL)
    }

    // Status
    pub fn status_running() -> Style {
        Style::default().fg(colors::SUCCESS).add_modifier(Modifier::BOLD)
    }

    pub fn status_stopped() -> Style {
        Style::default().fg(colors::ERROR).add_modifier(Modifier::BOLD)
    }

    pub fn status_starting() -> Style {
        Style::default().fg(colors::WARNING).add_modifier(Modifier::BOLD | Modifier::SLOW_BLINK)
    }

    // Selection
    pub fn selected() -> Style {
        Style::default()
            .fg(colors::BRAND_WHITE)
            .bg(Color::Rgb(0xE6, 0x39, 0x46))
    }

    // Help text
    pub fn help() -> Style {
        Style::default().fg(colors::TEXT_MUTED)
    }

    // Code
    pub fn code() -> Style {
        Style::default().fg(colors::BRAND_ORANGE)
    }

    pub fn code_bg() -> Style {
        Style::default().bg(colors::SLATE_CANVAS)
    }
}

/// Box drawing characters for consistent borders
pub mod box_drawing {
    // Rounded (default)
    pub const ROUNDED: &[&str] = &["╭", "─", "╮", "│", "╯", "─", "╰", "│"];
    // Square
    pub const SQUARE: &[&str] = &["┌", "─", "┐", "│", "┘", "─", "└", "│"];
    // Heavy
    pub const HEAVY: &[&str] = &["╔", "═", "╗", "║", "╝", "═", "╚", "║"];
    // Double
    pub const DOUBLE: &[&str] = &["╔", "═", "╗", "║", "╝", "═", "╚", "║"];
    // Dashed
    pub const DASHED: &[&str] = &["┌", "┄", "┐", "┆", "┘", "┄", "└", "┆"];

    pub fn get(style: &str) -> &'static [&'static str] {
        match style {
            "rounded" => ROUNDED,
            "square" => SQUARE,
            "heavy" => HEAVY,
            "double" => DOUBLE,
            "dashed" => DASHED,
            _ => ROUNDED,
        }
    }
}

/// Ember gradient helper for text
pub fn ember_gradient(text: &str) -> Vec<Line<'static>> {
    use ratatui::text::Span;
    let chars: Vec<char> = text.chars().collect();
    let len = chars.len().max(1);
    let mut lines = Vec::new();
    let mut spans = Vec::new();

    for (i, ch) in chars.iter().enumerate() {
        let t = i as f32 / (len - 1).max(1) as f32;
        let color = if t < 0.5 {
            // Red to mid
            let ratio = t * 2.0;
            Color::Rgb(
                (0xE6 as f32 * (1.0 - ratio) + 0xF0 as f32 * ratio) as u8,
                (0x39 as f32 * (1.0 - ratio) + 0x5A as f32 * ratio) as u8,
                (0x46 as f32 * (1.0 - ratio) + 0x3E as f32 * ratio) as u8,
            )
        } else {
            // Mid to orange
            let ratio = (t - 0.5) * 2.0;
            Color::Rgb(
                (0xF0 as f32 * (1.0 - ratio) + 0xFF as f32 * ratio) as u8,
                (0x5A as f32 * (1.0 - ratio) + 0x8A as f32 * ratio) as u8,
                (0x3E as f32 * (1.0 - ratio) + 0x3D as f32 * ratio) as u8,
            )
        };
        spans.push(Span::styled(ch.to_string(), Style::default().fg(color).add_modifier(ratatui::style::Modifier::BOLD)));
    }

    lines.push(Line::from(spans));
    lines
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_ember_gradient() {
        let lines = ember_gradient("BIFANG");
        assert_eq!(lines.len(), 1);
        assert!(!lines[0].spans.is_empty());
    }

    #[test]
    fn test_colors() {
        assert_eq!(colors::BRAND_RED, Color::Rgb(0xE6, 0x39, 0x46));
        assert_eq!(colors::SLATE_CANVAS, Color::Rgb(0x0F, 0x17, 0x2A));
    }
}