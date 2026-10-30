//! Opencode-Inspired Status Line for Bifang TUI
//!
//! Premium status line with live metrics, sparklines, and animations
//! inspired by Claude Code's frontier UX patterns.

use ratatui::{
    layout::{Constraint, Direction, Layout, Rect, Alignment},
    widgets::Paragraph,
    style::{Style, Modifier},
    text::{Line, Span},
    Frame,
};
use crate::design::{styles, colors};

/// Status metrics for display
pub struct StatusMetrics {
    pub tokens_used: u64,
    pub tokens_limit: u64,
    pub request_latency_ms: u64,
    pub model_name: String,
    pub active_workflow: bool,
    pub approval_pending: bool,
}

/// Sparkline data for token usage
pub struct Sparkline {
    data: Vec<u64>,
    max_points: usize,
}

impl Sparkline {
    pub fn new(max_points: usize) -> Self {
        Self {
            data: Vec::with_capacity(max_points),
            max_points,
        }
    }

    pub fn push(&mut self, value: u64) {
        if self.data.len() >= self.max_points {
            self.data.remove(0);
        }
        self.data.push(value);
    }

    pub fn render(&self, width: usize) -> String {
        if self.data.is_empty() {
            return "░".repeat(width);
        }

        let max = self.data.iter().max().copied().unwrap_or(1);
        let chars = ['▁', '▂', '▃', '▄', '▅', '▆', '▇', '█'];
        
        let mut result = String::new();
        for i in 0..width {
            let idx = (i * self.data.len()) / width;
            let value = self.data.get(idx).copied().unwrap_or(0);
            let height = ((value as f32 / max as f32) * (chars.len() - 1) as f32) as usize;
            result.push(chars[height.min(chars.len() - 1)]);
        }
        result
    }
}

/// Draw premium status line with metrics
pub fn draw_status_line(f: &mut Frame, area: Rect, metrics: &StatusMetrics, sparkline: &Sparkline) {
    let chunks = Layout::default()
        .direction(Direction::Horizontal)
        .constraints([
            Constraint::Length(12), // Model name
            Constraint::Length(40), // Sparkline
            Constraint::Min(20),    // Tokens used
            Constraint::Length(15), // Latency
            Constraint::Length(10), // Status indicator
        ])
        .split(area);

    // Model name
    let model_widget = Paragraph::new(Line::from(vec![
        Span::styled("◆ ", styles::text_ember()),
        Span::styled(&metrics.model_name, styles::text_primary().add_modifier(Modifier::BOLD)),
    ]))
    .alignment(Alignment::Left);

    f.render_widget(model_widget, chunks[0]);

    // Token sparkline
    let sparkline_text = sparkline.render(20);
    let sparkline_widget = Paragraph::new(Line::from(vec![
        Span::styled(&sparkline_text, Style::default().fg(colors::BRAND_ORANGE)),
    ]))
    .alignment(Alignment::Left);

    f.render_widget(sparkline_widget, chunks[1]);

    // Tokens used
    let token_pct = (metrics.tokens_used as f32 / metrics.tokens_limit as f32 * 100.0) as u64;
    let token_color = if token_pct > 90 {
        colors::ERROR
    } else if token_pct > 70 {
        colors::WARNING
    } else {
        colors::SUCCESS
    };

    let tokens_widget = Paragraph::new(Line::from(vec![
        Span::styled(format!("Tokens: {} / {}", metrics.tokens_used, metrics.tokens_limit), 
            Style::default().fg(token_color)),
    ]))
    .alignment(Alignment::Left);

    f.render_widget(tokens_widget, chunks[2]);

    // Latency
    let latency_widget = Paragraph::new(Line::from(vec![
        Span::styled("⏱ ", styles::text_muted()),
        Span::styled(format!("{}ms", metrics.request_latency_ms), 
            Style::default().fg(colors::INFO)),
    ]))
    .alignment(Alignment::Left);

    f.render_widget(latency_widget, chunks[3]);

    // Status indicator with animation
    let status_char = if metrics.active_workflow {
        "●" // Active workflow
    } else {
        "○" // Idle
    };

    let status_style = if metrics.approval_pending {
        styles::text_warning().add_modifier(Modifier::SLOW_BLINK)
    } else if metrics.active_workflow {
        styles::text_success()
    } else {
        styles::text_muted()
    };

    let status_widget = Paragraph::new(Line::from(vec![
        Span::styled(status_char, status_style),
    ]))
    .alignment(Alignment::Right);

    f.render_widget(status_widget, chunks[4]);
}

/// Spinner animations (like opencode's loading states)
pub mod spinner {
    const DOTS: &[&str] = &["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"];
    const BRAILLE_DOTS: &[&str] = &["⡀", "⡁", "⡃", "⡇", "⢇", "⣇", "⣧", "⣷", "⣿"];
    
    pub fn dot(frame: usize) -> &'static str {
        DOTS[frame % DOTS.len()]
    }
    
    pub fn braille(frame: usize) -> &'static str {
        BRAILLE_DOTS[frame % BRAILLE_DOTS.len()]
    }
}

/// Animated progress bar
pub fn progress_bar(progress: f32, width: usize, animated: bool) -> String {
    let filled = (progress * width as f32) as usize;
    let empty = width - filled;
    
    let fill_char = if animated { "█" } else { "━" };
    let empty_char = "─";
    
    format!("{}{}", fill_char.repeat(filled), empty_char.repeat(empty))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_sparkline() {
        let mut sparkline = Sparkline::new(10);
        sparkline.push(5);
        sparkline.push(10);
        sparkline.push(15);
        
        let rendered = sparkline.render(10);
        assert_eq!(rendered.len(), 10);
    }

    #[test]
    fn test_progress_bar() {
        let bar = progress_bar(0.5, 10, false);
        assert_eq!(bar.len(), 10);
    }
}
