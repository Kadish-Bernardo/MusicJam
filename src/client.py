import socket
import pickle
import struct
import zlib
import sounddevice as sd
import numpy as np
import threading

SERVER_IP = '172.20.10.5'  # IP do servidor
AUDIO_PORT = 5050
COMMAND_PORT = 5051

# Buffer de áudio compartilhado
buffer = []
buffer_lock = threading.Lock()

play_flag = threading.Event()
pause_flag = threading.Event()
stop_flag = threading.Event()

def receive_audio():
    global buffer
    try:
        audio_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        audio_sock.connect((SERVER_IP, AUDIO_PORT))
        print("[Cliente] Conectado ao servidor de áudio.")

        # Recebe sample rate
        sample_rate_data = audio_sock.recv(4)
        sample_rate = struct.unpack('I', sample_rate_data)[0]
        print(f"[Cliente] Sample rate: {sample_rate}")

        def audio_callback(outdata, frames, time_info, status):
            if stop_flag.is_set():
                raise sd.CallbackStop()
            if not play_flag.is_set() or pause_flag.is_set():
                # Envia silêncio se pausado
                outdata.fill(0)
                return

            with buffer_lock:
                if len(buffer) >= frames:
                    chunk = buffer[:frames]
                    del buffer[:frames]
                    outdata[:] = np.array(chunk).reshape(-1, 1)
                else:
                    # Buffer insuficiente: envia silêncio
                    outdata.fill(0)

        stream = sd.OutputStream(channels=1, samplerate=sample_rate, callback=audio_callback)
        stream.start()

        while not stop_flag.is_set():
            size_data = audio_sock.recv(4)
            if not size_data:
                break
            block_size = struct.unpack('I', size_data)[0]

            block_data = b''
            while len(block_data) < block_size:
                packet = audio_sock.recv(block_size - len(block_data))
                if not packet:
                    break
                block_data += packet

            decompressed = zlib.decompress(block_data)
            chunk = pickle.loads(decompressed)

            with buffer_lock:
                buffer.extend(chunk.tolist())

        stream.stop()
        audio_sock.close()
    except Exception as e:
        print(f"[Cliente] Erro na recepção de áudio: {e}")
        stop_flag.set()

def send_commands():
    try:
        cmd_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        cmd_sock.connect((SERVER_IP, COMMAND_PORT))
        print("[Cliente] Conectado ao servidor de comandos.")

        while not stop_flag.is_set():
            cmd = input("Comando (play, pause, resume, next, sair): ").strip().lower()
            if cmd in ['play', 'pause', 'resume', 'next', 'sair']:
                cmd_sock.sendall(cmd.encode())

                # Ajusta flags locais para controle do player
                if cmd == 'play' or cmd == 'resume':
                    play_flag.set()
                    pause_flag.clear()
                elif cmd == 'pause':
                    pause_flag.set()
                elif cmd == 'sair':
                    stop_flag.set()
                    break
            else:
                print("[Cliente] Comando inválido.")

        cmd_sock.close()
    except Exception as e:
        print(f"[Cliente] Erro ao enviar comando: {e}")
        stop_flag.set()

def main():
    play_flag.clear()
    pause_flag.set()
    stop_flag.clear()

    threading.Thread(target=receive_audio, daemon=True).start()
    threading.Thread(target=send_commands, daemon=True).start()

    # Mantém o programa rodando até o stop_flag ser setado
    while not stop_flag.is_set():
        try:
            threading.Event().wait(0.5)
        except KeyboardInterrupt:
            print("[Cliente] Interrompido pelo usuário.")
            stop_flag.set()

if __name__ == "__main__":
    main()
