//! Bifang TUI - UI Components
//!
//! Reusable widgets for the TUI application.

use ratatui::{
    layout::{Constraint, Direction, Layout, Rect, Alignment, Margin},
    widgets::{Block, Borders, Paragraph, List, ListItem, ListState, Tabs, BorderType, Clear, Wrap, Scrollbar, ScrollbarOrientation, ScrollbarState},
    style::{Style, Color, Modifier},
    text::{Line, Span, Text},
    Frame,
};
use crate::app::App;
use crate::types::{AppMode, ServerStatus, Tab, ChatMessage, MessageRole, FileEntry, DiffHunk, DiffLine, DiffKind, ApprovalRequest, RiskLevel};
use crate::design::{styles, colors, box_drawing, ember_gradient};

/// Draw the main application layout
pub fn draw_app(f: &mut Frame, app: &App) {
    let size = f.size();

    // Main layout: header, body, footer
    let chunks = Layout::default()
        .direction(Direction::Vertical)
        .constraints([
            Constraint::Length(3),  // Header with tabs
            Constraint::Min(10),    // Main content
            Constraint::Length(3),  // Footer/status
        ])
        .split(size);

    draw_header(f, app, chunks[0]);
    draw_body(f, app, chunks[1]);
    draw_footer(f, app, chunks[2]);

    // Overlays
    if app.command_palette_open {
        draw_command_palette(f, app, size);
    }

    if app.approval_pending.is_some() {
        draw_approval_dialog(f, app, size);
    }
}

/// Draw header with tabs and server status
fn draw_header(f: &mut Frame, app: &App, area: Rect) {
    let header_chunks = Layout::default()
        .direction(Direction::Horizontal)
        .constraints([
            Constraint::Percentage(60), // Tabs
            Constraint::Percentage(40), // Server status
        ])
        .split(area);

    // Tabs
    let tab_titles: Vec<Line> = app.tabs.iter().map(|tab| {
        Line::styled(tab.title(), styles::text_secondary())
    }).collect();

    let tabs = Tabs::new(tab_titles)
        .block(Block::default().borders(Borders::NONE))
        .highlight_style(styles::text_primary().add_modifier(Modifier::BOLD))
        .divider("  ")
        .select(app.active_tab);

    f.render_widget(tabs, header_chunks[0]);

    // Server status
    let status_text = match app.server_status {
        ServerStatus::Running => {
            let dot = "●";
            Line::from(vec![
                Span::styled(dot, styles::status_running()),
                Span::raw(" "),
                Span::styled("Connected", styles::text_success()),
            ])
        }
        ServerStatus::Starting => {
            Line::from(vec![
                Span::styled("◐", styles::status_starting()),
                Span::raw(" "),
                Span::styled("Starting...", styles::text_warning()),
            ])
        }
        ServerStatus::Error => {
            Line::from(vec![
                Span::styled("●", styles::status_stopped()),
                Span::raw(" "),
                Span::styled("Error", styles::text_error()),
            ])
        }
        ServerStatus::Stopped => {
            Line::from(vec![
                Span::styled("●", styles::status_stopped()),
                Span::raw(" "),
                Span::styled("Stopped", styles::text_muted()),
            ])
        }
    };

    let status_block = Paragraph::new(status_text)
        .alignment(Alignment::Right)
        .block(Block::default().borders(Borders::NONE));

    f.render_widget(status_block, header_chunks[1]);
}

/// Draw main body based on mode
fn draw_body(f: &mut Frame, app: &App, area: Rect) {
    match app.mode {
        AppMode::Workspace => draw_workspace(f, app, area),
        AppMode::Terminal => draw_terminal(f, app, area),
        AppMode::Files => draw_files(f, app, area),
        AppMode::Settings => draw_settings(f, app, area),
        AppMode::CommandPalette => {} // Handled as overlay
    }
}

/// Draw workspace (chat + diff split)
fn draw_workspace(f: &mut Frame, app: &App, area: Rect) {
    // Split: sidebar (files), main (chat/diff)
    let main_chunks = Layout::default()
        .direction(Direction::Horizontal)
        .constraints([
            Constraint::Length(35), // File explorer sidebar
            Constraint::Min(60),    // Main content
        ])
        .split(area);

    draw_file_sidebar(f, app, main_chunks[0]);
    draw_main_content(f, app, main_chunks[1]);
}

/// Draw file explorer sidebar
fn draw_file_sidebar(f: &mut Frame, app: &App, area: Rect) {
    let items: Vec<ListItem> = app.workspace_files.iter().enumerate().map(|(i, file)| {
        let icon = if file.is_dir { "📁" } else { "📄" };
        let style = if app.selected_file == Some(i) {
            styles::selected()
        } else {
            styles::text_secondary()
        };
        let name = if file.is_dir { format!("{}/", file.name) } else { file.name.clone() };
        ListItem::new(Line::from(vec![
            Span::raw(format!("{} ", icon)),
            Span::styled(name, style),
        ]))
    }).collect();

    let list = List::new(items)
        .block(Block::default()
            .title(" Files ")
            .title_style(styles::text_muted())
            .borders(Borders::ALL)
            .border_type(BorderType::Rounded)
            .border_style(styles::border_default()))
        .highlight_style(styles::selected())
        .highlight_symbol("▶ ");

    let mut state = ListState::default();
    state.select(app.selected_file);
    f.render_stateful_widget(list, area, &mut state);
}

/// Draw main content area (chat/diff)
fn draw_main_content(f: &mut Frame, app: &App, area: Rect) {
    let content_chunks = Layout::default()
        .direction(Direction::Vertical)
        .constraints([
            Constraint::Percentage(60), // Chat
            Constraint::Percentage(40), // Diff
        ])
        .split(area);

    draw_chat(f, app, content_chunks[0]);
    draw_diff(f, app, content_chunks[1]);
}

/// Draw chat panel
fn draw_chat(f: &mut Frame, app: &App, area: Rect) {
    let chat_chunks = Layout::default()
        .direction(Direction::Vertical)
        .constraints([
            Constraint::Min(5),   // Messages
            Constraint::Length(3), // Input
        ])
        .split(area);

    // Messages
    let messages: Vec<ListItem> = app.chat_messages.iter().map(|msg| {
        let (role_style, prefix) = match msg.role {
            MessageRole::User => (styles::text_primary(), "You"),
            MessageRole::Assistant => (styles::text_success(), "Bifang"),
            MessageRole::System => (styles::text_warning(), "System"),
            MessageRole::Tool => (styles::text_info(), "Tool"),
        };

        let timestamp = msg.timestamp.format("%H:%M").to_string();
        let header = Line::from(vec![
            Span::styled(prefix, role_style.add_modifier(Modifier::BOLD)),
            Span::raw(" "),
            Span::styled(timestamp, styles::text_muted()),
        ]);

        let content_lines: Vec<Line> = msg.content.lines().map(Line::raw).collect();
        let mut items = vec![header, Line::from("")];
        items.extend(content_lines);
        ListItem::new(items)
    }).collect();

    let list = List::new(messages)
        .block(Block::default()
            .title(" Chat ")
            .title_style(styles::text_muted())
            .borders(Borders::ALL)
            .border_type(BorderType::Rounded)
            .border_style(styles::border_default()))
        .style(styles::text_secondary());

    let mut state = ListState::default();
    state.select(Some(app.chat_messages.len().saturating_sub(1).min(app.chat_scroll)));
    f.render_stateful_widget(list, chat_chunks[0], &mut state);

    // Input
    let input_text = if app.chat_input.is_empty() {
        "Ask Bifang...".to_string()
    } else {
        app.chat_input.clone()
    };

    let input_style = if app.chat_input.is_empty() {
        styles::text_muted()
    } else {
        styles::text_primary()
    };

    let input = Paragraph::new(input_text)
        .style(input_style)
        .block(Block::default()
            .title(" Input (Enter=Send, Shift+Enter=Newline) ")
            .title_style(styles::text_muted())
            .borders(Borders::ALL)
            .border_type(BorderType::Rounded)
            .border_style(if app.chat_input.is_empty() { styles::border_default() } else { styles::border_focus() }));

    f.render_widget(input, chat_chunks[1]);
}

/// Draw diff panel
fn draw_diff(f: &mut Frame, app: &App, area: Rect) {
    if app.diff_hunks.is_empty() {
        let empty = Paragraph::new("No changes yet.\nStart a chat to see diffs.")
            .style(styles::text_muted())
            .alignment(Alignment::Center)
            .block(Block::default()
                .title(" Diff ")
                .title_style(styles::text_muted())
                .borders(Borders::ALL)
                .border_type(BorderType::Rounded)
                .border_style(styles::border_default()));
        f.render_widget(empty, area);
        return;
    }

    let lines: Vec<Line> = app.diff_hunks.iter().flat_map(|hunk| {
        let mut lines = Vec::new();
        lines.push(Line::from(vec![
            Span::styled(format!("@@ -{},{} +{},{} @@", hunk.old_start, hunk.old_lines, hunk.new_start, hunk.new_lines), styles::text_muted()),
        ]));
        for line in &hunk.lines {
            let (style, prefix) = match line.kind {
                DiffKind::Added => (styles::text_success(), "+ "),
                DiffKind::Removed => (styles::text_error(), "- "),
                DiffKind::Context => (styles::text_muted(), "  "),
            };
            lines.push(Line::from(vec![
                Span::styled(prefix, style),
                Span::styled(&line.content, style),
            ]));
        }
        lines
    }).collect();

    let diff_text = Text::from(lines);
    let paragraph = Paragraph::new(diff_text)
        .block(Block::default()
            .title(" Diff ")
            .title_style(styles::text_muted())
            .borders(Borders::ALL)
            .border_type(BorderType::Rounded)
            .border_style(styles::border_default()))
        .wrap(Wrap { trim: false })
        .scroll((app.diff_scroll as u16, 0));

    f.render_widget(paragraph, area);
}

/// Draw terminal panel
fn draw_terminal(f: &mut Frame, app: &App, area: Rect) {
    let term_chunks = Layout::default()
        .direction(Direction::Vertical)
        .constraints([
            Constraint::Min(10), // Terminal output
            Constraint::Length(3), // Input
        ])
        .split(area);

    if let Some(idx) = app.active_terminal {
        if idx < app.terminal_sessions.len() {
            let session = &app.terminal_sessions[idx];
            let output: Vec<Line> = session.buffer.iter()
                .rev()
                .take(area.height as usize - 3)
                .rev()
                .map(|line| Line::raw(line.clone()))
                .collect();

            let terminal = Paragraph::new(output)
                .style(styles::code_bg())
                .block(Block::default()
                    .title(format!(" Terminal: {} ", session.cwd))
                    .title_style(styles::text_muted())
                    .borders(Borders::ALL)
                    .border_type(BorderType::Rounded)
                    .border_style(styles::border_default()));
            f.render_widget(terminal, term_chunks[0]);

            // Input
            let input = Paragraph::new(app.terminal_input.as_str())
                .style(styles::text_primary())
                .block(Block::default()
                    .title(" Command ")
                    .title_style(styles::text_muted())
                    .borders(Borders::ALL)
                    .border_type(BorderType::Rounded)
                    .border_style(styles::border_focus()));
            f.render_widget(input, term_chunks[1]);
        }
    } else {
        let empty = Paragraph::new("Press Ctrl+` to open terminal")
            .style(styles::text_muted())
            .alignment(Alignment::Center);
        f.render_widget(empty, area);
    }
}

/// Draw files panel
fn draw_files(f: &mut Frame, app: &App, area: Rect) {
    let items: Vec<ListItem> = app.workspace_files.iter().enumerate().map(|(i, file)| {
        let icon = if file.is_dir { "📁" } else { "📄" };
        let style = if app.selected_file == Some(i) {
            styles::selected()
        } else {
            styles::text_secondary()
        };
        let name = if file.is_dir { format!("{}/", file.name) } else { file.name.clone() };
        ListItem::new(Line::from(vec![
            Span::raw(format!("{} ", icon)),
            Span::styled(name, style),
        ]))
    }).collect();

    let list = List::new(items)
        .block(Block::default()
            .title(" Files ")
            .title_style(styles::text_muted())
            .borders(Borders::ALL)
            .border_type(BorderType::Rounded)
            .border_style(styles::border_default()))
        .highlight_style(styles::selected())
        .highlight_symbol("▶ ");

    let mut state = ListState::default();
    state.select(app.selected_file);
    f.render_stateful_widget(list, area, &mut state);
}

/// Draw settings panel
fn draw_settings(f: &mut Frame, app: &App, area: Rect) {
    let settings = vec![
        ("Server URL", app.server_url.as_str()),
        ("Workspace", app.workspace_path.as_deref().unwrap_or("Not set")),
        ("Server Status", match app.server_status { ServerStatus::Running => "Running", ServerStatus::Starting => "Starting", ServerStatus::Stopped => "Stopped", ServerStatus::Error => "Error" }),
        ("Theme", "Bifang Dark (fixed)"),
        ("Font", "JetBrains Mono (terminal)"),
    ];

    let items: Vec<ListItem> = settings.into_iter().map(|(key, value)| {
        ListItem::new(Line::from(vec![
            Span::styled(format!("{}: ", key), styles::text_muted()),
            Span::styled(value, styles::text_primary()),
        ]))
    }).collect();

    let list = List::new(items)
        .block(Block::default()
            .title(" Settings ")
            .title_style(styles::text_muted())
            .borders(Borders::ALL)
            .border_type(BorderType::Rounded)
            .border_style(styles::border_default()));

    f.render_widget(list, area);
}

/// Draw footer/status bar
fn draw_footer(f: &mut Frame, app: &App, area: Rect) {
    let footer_chunks = Layout::default()
        .direction(Direction::Horizontal)
        .constraints([
            Constraint::Percentage(70), // Status message
            Constraint::Percentage(30), // Shortcuts
        ])
        .split(area);

    // Status message
    let status = app.status_message.as_deref().unwrap_or("Ready");
    let status_widget = Paragraph::new(status)
        .style(styles::text_secondary())
        .block(Block::default().borders(Borders::NONE));
    f.render_widget(status_widget, footer_chunks[0]);

    // Shortcuts
    let shortcuts = Line::from(vec![
        Span::styled("Ctrl+N", styles::help()), Span::raw(" New  "),
        Span::styled("Ctrl+O", styles::help()), Span::raw(" Open  "),
        Span::styled("Ctrl+`", styles::help()), Span::raw(" Terminal  "),
        Span::styled("Ctrl+B", styles::help()), Span::raw(" Files  "),
        Span::styled("Ctrl+P", styles::help()), Span::raw(" Commands  "),
        Span::styled("Ctrl+Q", styles::help()), Span::raw(" Quit"),
    ]);
    let shortcuts_widget = Paragraph::new(shortcuts)
        .alignment(Alignment::Right)
        .block(Block::default().borders(Borders::NONE));
    f.render_widget(shortcuts_widget, footer_chunks[1]);
}

/// Draw command palette overlay
fn draw_command_palette(f: &mut Frame, app: &App, area: Rect) {
    let popup_area = centered_rect(60, 40, area);
    f.render_widget(Clear, popup_area);

    let input = Paragraph::new(format!("> {}", app.command_palette_query))
        .style(styles::text_primary())
        .block(Block::default()
            .title(" Commands ")
            .title_style(styles::text_ember())
            .borders(Borders::ALL)
            .border_type(BorderType::Rounded)
            .border_style(styles::border_focus()));

    let input_area = Layout::default()
        .direction(Direction::Vertical)
        .constraints([Constraint::Length(3), Constraint::Min(5)])
        .split(popup_area)[0];

    f.render_widget(input, input_area);

    // Results
    let items: Vec<ListItem> = app.command_palette_results.iter().map(|cmd| {
        let title = cmd.title.clone();
        let desc = cmd.description.clone();
        let shortcut = cmd.shortcut.as_deref().unwrap_or("");
        ListItem::new(Line::from(vec![
            Span::styled(title, styles::text_primary()),
            Span::raw("  "),
            Span::styled(desc, styles::text_muted()),
            Span::raw("  "),
            Span::styled(shortcut, styles::help()),
        ]))
    }).collect();

    let list = List::new(items)
        .block(Block::default()
            .borders(Borders::ALL)
            .border_type(BorderType::Rounded)
            .border_style(styles::border_default()));

    let list_area = Layout::default()
        .direction(Direction::Vertical)
        .constraints([Constraint::Length(3), Constraint::Min(5)])
        .split(popup_area)[1];

    f.render_widget(list, list_area);
}

/// Draw approval dialog overlay
fn draw_approval_dialog(f: &mut Frame, app: &App, area: Rect) {
    if let Some(approval) = &app.approval_pending {
        let popup_area = centered_rect(70, 30, area);
        f.render_widget(Clear, popup_area);

        let risk_color = match approval.risk_level {
            RiskLevel::Low => styles::text_success(),
            RiskLevel::Medium => styles::text_warning(),
            RiskLevel::High => styles::text_error(),
            RiskLevel::Critical => styles::btn_destructive(),
        };

        let text = Text::from(vec![
            Line::from(vec![
                Span::styled("⚠ Permission Required", styles::text_ember_strong()),
            ]),
            Line::from(""),
            Line::from(vec![
                Span::styled("Action: ", styles::text_muted()),
                Span::styled(&approval.action, styles::text_primary()),
            ]),
            Line::from(vec![
                Span::styled("Description: ", styles::text_muted()),
                Span::styled(&approval.description, styles::text_secondary()),
            ]),
            Line::from(""),
            Line::from(vec![
                Span::styled("Risk: ", styles::text_muted()),
                Span::styled(format!("{:?}", approval.risk_level), risk_color.add_modifier(Modifier::BOLD)),
            ]),
            Line::from(""),
            Line::from(vec![
                Span::styled("Press ", styles::help()),
                Span::styled("Y", styles::btn_success().add_modifier(Modifier::BOLD)),
                Span::styled(" to allow, ", styles::help()),
                Span::styled("N", styles::btn_destructive().add_modifier(Modifier::BOLD)),
                Span::styled(" to deny", styles::help()),
            ]),
        ]);

        let paragraph = Paragraph::new(text)
            .block(Block::default()
                .title(" Approval ")
                .title_style(styles::text_ember())
                .borders(Borders::ALL)
                .border_type(BorderType::Rounded)
                .border_style(styles::border_error()))
            .wrap(Wrap { trim: false });

        f.render_widget(paragraph, popup_area);
    }
}

/// Helper to create centered rect
fn centered_rect(percent_x: u16, percent_y: u16, r: Rect) -> Rect {
    let popup_layout = Layout::default()
        .direction(Direction::Vertical)
        .constraints([
            Constraint::Percentage((100 - percent_y) / 2),
            Constraint::Percentage(percent_y),
            Constraint::Percentage((100 - percent_y) / 2),
        ])
        .split(r);

    Layout::default()
        .direction(Direction::Horizontal)
        .constraints([
            Constraint::Percentage((100 - percent_x) / 2),
            Constraint::Percentage(percent_x),
            Constraint::Percentage((100 - percent_x) / 2),
        ])
        .split(popup_layout[1])[1]
}