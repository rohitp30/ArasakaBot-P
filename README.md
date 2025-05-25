# Arasaka Discord Bot

Currently tailored to the Arasaka community but has automated spreadsheet capabilities, advanced point updating commands, and other misc capabilities.

## Features

- Automated spreadsheet integration with Google Sheets
- XP and rank management system
- Event logging and tracking
- Discord ↔ Roblox account linking
- Administrative commands for bot management

## Installation

1. Clone the repository:
   ```bash
   git clone https://github.com/yourusername/ArasakaBot.git
   cd ArasakaBot
   ```

2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

3. Create a `.env` file with the following variables:
   ```
   AC_PREFIX=!
   TOKEN=your_discord_bot_token
   DSN_SENTRY=your_sentry_dsn
   BLOXLINK_TOKEN=your_bloxlink_token
   ROBLOX_SECURITY=your_roblox_security_token
   OPENAI_API=your_openai_api_key
   ```

4. Create a `ArasakaBotCreds.json` file with your Google Sheets API credentials.

5. Run the bot:
   ```bash
   python main.py
   ```

## Testing

The bot includes a comprehensive test suite using pytest and dpytest.

### Running Tests Locally

1. Install test dependencies:
   ```bash
   pip install -r requirements-test.txt
   ```

2. Run the tests:
   ```bash
   pytest tests/
   ```

3. Generate a coverage report:
   ```bash
   coverage run -m pytest tests/
   coverage report
   ```

### Continuous Integration

This project uses GitHub Actions for continuous integration. Tests are automatically run on push to the main branch and on pull requests.

## Project Structure

- `main.py`: The main bot file
- `core/`: Core functionality modules
- `utils/`: Cog files for different bot features
- `tests/`: Test files for the bot
