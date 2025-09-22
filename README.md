# Cards Grid Preview

An Anki add-on that displays all cards from the currently selected deck in a customizable, paginated grid view. Perfect for previewing at a glance all the cards in a visual deck.

## Features

- **Responsive grid layout**: Adjustable columns and rows per page
- **Card customization**:
  - Variable card size and font size
  - Adjustable aspect ratio from tall to wide formats
- **Interactive flipping**:
  - Hover over cards to see the back side with smooth 3D animation
  - Click cards to manually flip them
  - Toggle "Flip all" to show all answers at once
- **Smart pagination**: Navigate large decks efficiently with page controls
- **Full LaTeX and media support**:
  - Complete MathJax v3 with Anki's default packages (ams, mathtools, physics, braket, cancel, color)
  - Supports both `\( \)` and `$ $` for inline math, `\[ \]` for display math

> [!WARNING]  
> Images, audio, and other media are not supported.

## Usage

1. Select any deck in Anki's main window
2. Open via **Tools → Cards Grid Preview** or press **Ctrl+Shift+G**
3. Use the toolbar to customize:
   - Adjust grid dimensions and card size
   - Change font size and aspect ratio
   - Navigate between pages for large decks
   - Toggle flip-all mode

## Notes

- Cards render using their actual front/back templates (same as review mode)
- Pagination automatically adjusts when you change grid dimensions
- Great for visual learners and deck overview sessions
- Works with all card types including cloze deletions

## Requirements

Anki 2.1.50+ (Qt5/Qt6)

## Development

- Files live in `addons21/cards_grid_preview`.
- On change, restart Anki (or use the Add-ons screen → View Files → "Reload Add-ons").

## License

MIT
