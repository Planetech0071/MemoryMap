# MemoryMap Camera & Phone Connection Guide

## � Quick Start

Simply run:
```bash
python main.py
```

You'll be asked to choose:
- **Option 1:** Use your computer's webcam
- **Option 2:** Connect your iPhone camera using Shortcuts

## 📷 Option 1: Computer Webcam

1. Run `python main.py`
2. Choose **Option 1**
3. MemoryMap will start analyzing your webcam in real-time
4. Type questions to ask about what you see:
   - "Where are my keys?"
   - "What's on my desk?"
   - "Did I move my phone?"

Press `Ctrl+C` to stop.

## 📱 Option 2: iPhone Camera with Shortcuts

### Setup (One-time only)

1. **Start MemoryMap:**
   ```bash
   python main.py
   ```

2. **Choose Option 2** when prompted

3. **On your iPhone:**
   - Open the **Shortcuts app**
   - Tap **"Create Shortcut"** or **"+"**
   - Visit the setup page shown in terminal (or scan QR code):
     ```
     http://<your-computer-ip>:8000/phone-stream
     ```
   - Follow the step-by-step instructions to create the shortcut

4. **The shortcut will:**
   - Capture photos from your camera every 1-2 seconds
   - Send them to MemoryMap for analysis
   - Run in a loop (keep tapping to capture continuously)

### Your Endpoint URL

Replace `YOUR_IP` in the shortcut with your computer's IP shown in the terminal:
```
http://YOUR_IP:8000/observe
```

## ❓ Asking Questions

While the camera is running (webcam or phone), simply type your questions:

```
❓ Ask: Where are my keys?
✓ Answer: I last saw your keys on the desk 2 minutes ago.

❓ Ask: What's in this room?
✓ Answer: I can see a laptop, phone, coffee cup, and notebook on the desk.

❓ Ask: Did I move my wallet?
✓ Answer: Yes, I saw your wallet move from the desk to the drawer 5 minutes ago.
```

## 🔧 How It Works

### Webcam Mode (Option 1)
- Analyzes video frames in real-time
- Updates memory as objects move
- Responds to questions about what it sees

### iPhone Mode (Option 2)
- Uses native iPhone Shortcuts app
- Sends photos from your phone's camera
- No external apps required
- Works over local WiFi connection

## 📍 Phone & Computer Must Be on Same WiFi

Both devices need to be connected to the same WiFi network for the iPhone shortcut to reach your computer.

## ❌ Troubleshooting

**"Error sending photo"**
- Check that phone and computer are on same WiFi
- Verify IP address in the shortcut matches terminal output
- Make sure firewall allows port 8000

**"Camera not available"**
- Make sure you granted camera permissions
- Close and reopen the browser/shortcut
- Try restarting the app

**Can't find computer IP**
- Look at terminal output when you start MemoryMap
- Should show something like `192.168.x.x` or `127.0.0.1`

**Shortcut keeps asking for permissions**
- Go to iPhone Settings > Shortcuts > Allow Untrusted Shortcuts
- This allows the shortcut to run without confirmation each time

## 📚 Features

✅ Real-time object detection  
✅ Memory storage (what did I see and where)  
✅ Movement tracking (did it move?)  
✅ Time awareness (when did I last see it?)  
✅ Zone detection (which room/area?)  
✅ Natural language queries (just ask!)

