```markdown
# M3U8 Telegram Bot

A Telegram bot that downloads M3U8 video playlists, merges segments into MP4 files, and uploads them to Telegram.

## Features

- ✅ Download M3U8 playlists and merge segments
- ✅ Custom file naming with `|` separator
- ✅ Progress updates during processing
- ✅ Automatic file splitting for large videos (>2GB)
- ✅ Works in private chats, groups, and channels
- ✅ Comprehensive error handling
- ✅ Deploy as Render Background Worker

## Usage

### Basic URL
```
https://example.com/playlist.m3u8
```

### Custom Filename
```
https://example.com/playlist.m3u8|My Custom Video.mp4
```

## Commands

- `/start` - Show welcome message
- `/help` - Show help message

## Deployment

### Environment Variables
```
API_ID=your_api_id
API_HASH=your_api_hash
BOT_TOKEN=your_bot_token
```

### Render Background Worker
1. Connect GitHub repository
2. Create Background Worker
3. Set environment variables
4. Deploy with Docker

## Requirements

- Python 3.11+
- FFmpeg
- Telegram Bot Token
- Telegram API credentials

## License

MIT License
```
