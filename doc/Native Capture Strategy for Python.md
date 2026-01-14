This strategy represents the most robust long-term fix for Whisperflow because it aligns the application's data path (how it gets audio) with the OS's control path (how the user selects audio). By dropping the sounddevice (ALSA/PortAudio) dependency for Bluetooth, you bypass the layer responsible for "hiding" the idle device.

The following is a technical breakdown and implementation guide for the **Native Capture Strategy** using a Python subprocess shim.

### **1\. Architectural Justification**

The core failure in the current architecture is an "Enumeration Gap."

* **Current Path:** App → sounddevice → PortAudio → ALSA API → PipeWire-ALSA Plugin → PipeWire.  
  * *Failure Point:* The PipeWire-ALSA Plugin is designed to mimic hardware. If a Bluetooth device is "suspended" (saving battery), the plugin often reports it as unplugged or invisible to satisfy legacy ALSA constraints.  
* **Native Path:** App → pw-record → PipeWire.  
  * *Advantage:* pw-record is a native PipeWire client. When it requests a connection to a specific node (even a suspended one), it triggers a "Demand" event. The session manager (WirePlumber) sees this demand and immediately wakes the Bluetooth device, renegotiates the profile (HFP/HSP), and begins the stream.

### **2\. Implementation Strategy: The "Subprocess Shim"**

While direct C-bindings (ctypes) to libpipewire are possible, they are notoriously complex and unstable for Python applications due to the asynchronous MainLoop requirements of PipeWire. The industry-standard approach for Python (used by projects like ProcTap and manjaro-pipewire-gui) is wrapping the CLI tools.

#### **Step A: Resolve the Target**

You cannot simply record from "default" because you want to ensure you are capturing the *Bluetooth* device the user selected, not the internal fallback.

Python

import subprocess

def get\_pipewire\_default\_source():  
    """  
    Queries the PulseAudio compatibility layer to find the name   
    of the device the user selected in the OS Settings.  
    """  
    try:  
        \# 'pactl' is the standard administration tool for PulseAudio/PipeWire-Pulse  
        result \= subprocess.run(  
            \["pactl", "get-default-source"\],  
            capture\_output=True,  
            text=True,  
            check=True  
        )  
        \# Returns string like: "bluez\_input.XX\_XX\_XX\_XX\_XX\_XX.0"  
        return result.stdout.strip()  
    except subprocess.CalledProcessError:  
        \# Fallback if pactl fails  
        return None

#### **Step B: The Capture Class**

This class replaces your existing sounddevice.InputStream. It spawns pw-record and reads raw PCM data from its standard output.

Python

import subprocess  
import signal

class PipeWireCapture:  
    def \_\_init\_\_(self, target\_device=None, rate=16000, channels=1, dtype='int16'):  
        self.target \= target\_device  
        self.rate \= rate  
        self.channels \= channels  
        self.process \= None  
          
        \# Map numpy/python types to pw-record format flags  
        self.format\_map \= {  
            'int16': 's16',  
            'float32': 'f32',  
        }  
        if dtype not in self.format\_map:  
            raise ValueError(f"Unsupported dtype: {dtype}")  
        self.pw\_format \= self.format\_map\[dtype\]  
          
        \# Calculate frame size for buffer management  
        \# s16 \= 2 bytes, f32 \= 4 bytes  
        self.sample\_width \= 2 if dtype \== 'int16' else 4  
        self.frame\_size \= self.sample\_width \* channels

    def start(self):  
        """Starts the native pw-record subprocess."""  
        cmd \=  
          
        \# If a specific target is provided (e.g. the Bluetooth headset), target it.  
        \# Otherwise, pw-record uses the system default (which might be the fallback mic).  
        if self.target:  
            cmd.extend(\["--target", self.target\])  
              
        self.process \= subprocess.Popen(  
            cmd,  
            stdout=subprocess.PIPE,  
            stderr=subprocess.PIPE, \# Capture stderr to hide logs or debug  
            bufsize=0 \# Unbuffered to reduce latency  
        )

    def read(self, num\_frames):  
        """  
        Reads 'num\_frames' from the stdout pipe.   
        Blocking call, similar to sounddevice.read().  
        """  
        if not self.process:  
            raise RuntimeError("Stream not started")  
              
        bytes\_to\_read \= num\_frames \* self.frame\_size  
        raw\_data \= self.process.stdout.read(bytes\_to\_read)  
          
        if len(raw\_data) \< bytes\_to\_read:  
            \# This indicates the pipe closed or device disconnected  
            raise RuntimeError("PipeWire stream ended unexpectedly")  
              
        return raw\_data

    def stop(self):  
        """Cleanly terminates the subprocess."""  
        if self.process:  
            self.process.terminate()  
            try:  
                self.process.wait(timeout=0.5)  
            except subprocess.TimeoutExpired:  
                self.process.kill()  
            self.process \= None

    def \_\_enter\_\_(self):  
        self.start()  
        return self

    def \_\_exit\_\_(self, exc\_type, exc\_val, exc\_tb):  
        self.stop()

### **3\. Key Advantages of This Implementation**

1. "Wake-on-Demand" Behavior:  
   When you run pw-record \--target bluez\_input..., PipeWire receives a graph update request. Even if the node is SUSPENDED, WirePlumber (the session manager) detects that a client (pw-record) needs data. It automatically sends the Bluetooth command to wake the radio and switch profiles from A2DP (Music) to HFP/HSP (Calls). sounddevice often fails to trigger this state change.1  
2. Format Agnosticism:  
   Bluetooth headsets operate at strange sample rates (e.g., 8000Hz for mSBC, 16000Hz for WBS). If you request 44.1kHz via sounddevice, and the hardware only supports 16kHz, ALSA often throws an error.  
   pw-record connects to the graph. PipeWire automatically inserts a resampler node between the headset (16k) and your app (48k). You always get the clean, requested rate without implementing resampling logic in Python.3  
3. Sandboxing Compatibility:  
   If you package Whisperflow as a Flatpak or Snap, direct hardware access (ALSA) is often blocked. pw-record communicates via the PipeWire socket, which is the supported protocol for containerized audio access.4

### **4\. Integration Logic (The "Hybrid" Approach)**

You don't need to rewrite the entire audio engine. You can use a hybrid resolver:

1. **Attempt 1 (Standard):** Query sounddevice. If the user-selected Bluetooth device appears explicitly by name, use it.  
2. **Attempt 2 (Fallback):** If pactl info shows a Bluetooth device is default, but sounddevice lists only "Generic ALSA", switch to the PipeWireCapture class defined above.  
3. **Latency Handling:** The first read() from the PipeWireCapture class might block for 1-2 seconds while the Bluetooth headset wakes up. Your UI thread should account for this (e.g., show a "Connecting..." spinner) to avoid freezing while self.process.stdout.read waits for the first bytes.

### **5\. Why Not Use pipewire\_python?**

You may find libraries like pipewire\_python or pypewire on PyPI. Research confirms these are often unmaintained or simply wrappers around subprocess similar to the code above, but with less control over buffering and error handling.5 Writing your own shim (as shown in Step B) is safer for production as it has zero external dependencies.

