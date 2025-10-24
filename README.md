# AI Video Downloader

An intelligent video downloader that automatically downloads and upscales your favorite videos. The program uses Playwright for browser automation and is fully configurable.

## ✨ Features

- 🚀 **Automatic Download** - Automatically downloads all videos from favorites
- 🔍 **Duplicate Detection** - Detects and skips already downloaded videos
- 📈 **Automatic Upscale** - Upscales videos to HD quality before download
- 🌐 **Multi-language Support** - English and Hungarian language support
- ⚙️ **Fully Configurable** - Extensive configuration options
- 🎯 **Smart Waiting** - Random wait times to avoid detection
- 🔄 **Error Handling** - Robust error handling and retry logic
- 📱 **Browser Emulation** - Real browser behavior simulation

## 📋 Requirements

- Python 3.12+
- Google Chrome or Chromium browser
- Internet connection

## 🚀 Installation

1. **Clone the repository:**
   ```bash
   git clone https://github.com/richardfoltin/AI-video-downloader.git
   cd AI-video-downloader
   ```

2. **Install dependencies:**
   ```bash
   pip install pipenv
   pipenv install
   ```

3. **Install Playwright browser:**
   ```bash
   pipenv run playwright install chrome
   ```

## ⚙️ Configuration

1. **Copy the example configuration:**
   ```bash
   cp .env.example .env
   ```

2. **Edit the .env file:**
   ```bash
   # Basic settings
   LANGUAGE=en  # or hu
   COOKIE_FILE=cookies.txt
   DOWNLOAD_DIR=downloads

   # Browser settings
   HEADLESS=false
   BROWSER_CHANNEL=chrome
   ```

### 🍪 Cookie File Setup

The program needs valid cookies to access your videos.

1. **Open in your browser:** `https://grok.com/imagine/favorites`

2. **Sign in** (if needed)

3. **Open developer tools:**
   - Chrome/Edge: `F12` or `Ctrl+Shift+I`
   - Firefox: `F12` or `Ctrl+Shift+I`

4. **Go to Application/Storage → Cookies → .grok.com**

5. **Copy all cookies** and save them to `cookies.txt` file in the following format:
   ```
   name1=value1; name2=value2; name3=value3
   ```

   Example:
   ```
   sso=abc123; sso-rw=def456; x-anonuserid=xyz789
   ```

## 🎬 Usage

1. **Activate virtual environment:**
   ```bash
   pipenv shell
   ```

2. **Run the program:**
   ```bash
   python download.py
   ```

The program will automatically:
- Open the favorites page
- Browse through all videos
- Upscale them to HD quality
- Download videos to the `downloads/` folder


## 🐛 Troubleshooting

### 403 Forbidden Error
- Check your cookie file
- Generate new cookies
- Make sure you're using the same user-agent

### No Videos Found
- Check if there's content on the favorites page
- Verify cookie validity
- Try increasing the `INITIAL_PAGE_WAIT_MS` value

### Slow Performance
- Increase wait times
- Use `HEADLESS=false` for visual feedback

### Memory Issues
- Reduce `VIEWPORT_WIDTH/HEIGHT` values
- Use `HEADLESS=true` mode

## 📝 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.
