//! Bifang TUI - Main Application Entry Point
//!
//! A terminal-native coding workspace with the same design identity as the desktop app.

use std::io;
use std::time::Duration;
use std::sync::Arc;
use tokio::sync::mpsc;
use crossterm::{
    event::{self, Event, KeyCode, KeyEvent, KeyModifiers, MouseEvent, MouseEventKind},
    terminal::{disable_raw_mode, enable_raw_mode, EnterAlternateScreen, LeaveAlternateScreen},
    execute,
};
use ratatui::{
    backend::CrosstermBackend,
    layout::{Constraint, Direction, Layout, Rect, Alignment, Margin},
    widgets::{Block, Borders, Paragraph, List, ListItem, ListState, Tabs, BorderType, Clear, Wrap},
    style::{Style, Color, Modifier},
    text::{Line, Span, Text},
    Frame, Terminal,
};
use anyhow::Result;

use bifang_tui::App;

#[tokio::main]
async fn main() -> Result<()> {
    // Initialize tracing
    tracing_subscriber::fmt()
        .with_env_filter(tracing_subscriber::EnvFilter::from_default_env())
        .with_target(false)
        .compact()
        .init();

    // Setup terminal
    enable_raw_mode()?;
    let mut stdout = io::stdout();
    execute!(stdout, EnterAlternateScreen)?;
    let backend = CrosstermBackend::new(stdout);
    let mut terminal = Terminal::new(backend)?;
    terminal.hide_cursor()?;

    // Create app state
    let mut app = App::new().await?;

    // Run app
    let result = run_app(&mut terminal, &mut app).await;

    // Cleanup
    disable_raw_mode()?;
    execute!(terminal.backend_mut(), LeaveAlternateScreen)?;
    terminal.show_cursor()?;

    result
}

async fn run_app<B: ratatui::backend::Backend>(terminal: &mut Terminal<B>, app: &mut App) -> Result<()> {
    let tick_rate = Duration::from_millis(50);
    let mut last_tick = std::time::Instant::now();

    loop {
        terminal.draw(|f| app.draw(f))?;

        let timeout = tick_rate.saturating_sub(last_tick.elapsed());
        if event::poll(timeout)? {
            if let Event::Key(key) = event::read()? {
                if app.handle_key(key).await? {
                    break; // Exit requested
                }
            } else if let Event::Mouse(mouse) = event::read()? {
                app.handle_mouse(mouse).await?;
            } else if let Event::Resize(_, _) = event::read()? {
                terminal.autoresize()?;
            }
        }

        if last_tick.elapsed() >= tick_rate {
            app.tick().await?;
            last_tick = std::time::Instant::now();
        }
    }

    Ok(())
}