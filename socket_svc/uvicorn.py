# These are *starter* selectors based on your screenshots + typical layouts.
# Expect to adjust once you inspect the live DOM with Playwright's devtools.

CRICKET_LIST_CONTAINER = 'section:has-text("Cricket"), div:has-text("Cricket")'
MATCH_ROW             = f'{CRICKET_LIST_CONTAINER} a:has-text("Live Now"), {CRICKET_LIST_CONTAINER} a:has([data-live])'
MATCH_TITLE           = 'a >> text=?'  # We'll read the <a> inner text.

# Inside a match page/panel:
BOOKMAKER_TABLE       = 'text=Bookmaker, table, [data-testid="bookmaker"]'
BOOKMAKER_ROWS        = f'{BOOKMAKER_TABLE} tr'
BOOK_BACK_CELL        = 'td:has-text("Back"), td:nth-of-type(2)'
BOOK_LAY_CELL         = 'td:has-text("Lay"), td:nth-of-type(3)'

FANCY_SECTION         = 'text=Fancy, [data-testid="fancy"]'
FANCY_ROW             = f'{FANCY_SECTION} tr, {FANCY_SECTION} .row'
FANCY_MARKET_CELL     = 'td:first-child, .market-label'
FANCY_YES_CELL        = 'td:has-text("Yes"), .yes'
FANCY_NO_CELL         = 'td:has-text("No"), .no'

SESSIONS_SECTION      = 'text=Session, [data-testid="session"]'
SESSIONS_ROW          = f'{SESSIONS_SECTION} tr, {SESSIONS_SECTION} .row'
SESSIONS_LABEL        = 'td:first-child, .label'
SESSIONS_YES          = 'td:has-text("Yes"), .yes'
SESSIONS_NO           = 'td:has-text("No"), .no'

RESULT_BADGE          = 'text=Result, [data-testid="result"], .result'
