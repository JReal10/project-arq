from __future__ import annotations
import asyncio
import os
from dotenv import load_dotenv
import numpy as np
import sounddevice as sd
import openai
from agents.voice import StreamedAudioInput, VoicePipeline
from util import MyWorkflow

# Load environment variables
load_dotenv()
openai.api_key = os.getenv("OPENAI_API_KEY")

CHUNK_LENGTH_S = 0.05  # 50ms
SAMPLE_RATE = 24000
FORMAT = np.int16
CHANNELS = 1


class TerminalVoiceApp:
    def __init__(self):
        self.should_send_audio = asyncio.Event()
        self.audio_input = StreamedAudioInput()
        self.audio_player = sd.OutputStream(
            samplerate=SAMPLE_RATE,
            channels=CHANNELS,
            dtype=FORMAT,
        )
        self.pipeline = VoicePipeline(
            workflow=MyWorkflow(
                secret_word="dog",
                on_start=self._on_transcription
            )
        )

    def _on_transcription(self, transcription: str) -> None:
        print(f"[Transcription] {transcription}")

    async def start(self):
        print("🎤 Starting voice agent terminal app...")
        await asyncio.gather(
            self.run_pipeline(),
            self.send_mic_audio(),
            self.input_loop()
        )

    async def run_pipeline(self):
        try:
            self.audio_player.start()
            result = await self.pipeline.run(self.audio_input)

            async for event in result.stream():
                if event.type == "voice_stream_event_audio":
                    self.audio_player.write(event.data)
                    print(f"[AudioStream] Received {len(event.data)} bytes")
                elif event.type == "voice_stream_event_lifecycle":
                  print(f"[Lifecycle] {event.event}")
        except Exception as e:
            print(f"[Error] {e}")
        finally:
            self.audio_player.close()

    async def send_mic_audio(self):
        stream = sd.InputStream(
            channels=CHANNELS,
            samplerate=SAMPLE_RATE,
            dtype=FORMAT,
        )
        stream.start()

        read_size = int(SAMPLE_RATE * 0.02)

        try:
            while True:
                if stream.read_available < read_size:
                    await asyncio.sleep(0.01)
                    continue

                await self.should_send_audio.wait()
                data, _ = stream.read(read_size)
                await self.audio_input.add_audio(data)
                await asyncio.sleep(0)
        except Exception as e:
            print(f"[MicError] {e}")
        finally:
            stream.stop()
            stream.close()

    async def input_loop(self):
        loop = asyncio.get_event_loop()
        while True:
            command = await loop.run_in_executor(None, input, "\n[Command] Press 'k' to toggle recording, 'q' to quit: ")
            if command.lower() == "k":
                if self.should_send_audio.is_set():
                    self.should_send_audio.clear()
                    print("[Status] 🎙️ Stopped recording.")
                else:
                    self.should_send_audio.set()
                    print("[Status] 🔴 Started recording.")
            elif command.lower() == "q":
                print("[Exit] Quitting...")
                self.should_send_audio.clear()
                self.audio_input.close()
                break


if __name__ == "__main__":
    asyncio.run(TerminalVoiceApp().start())
