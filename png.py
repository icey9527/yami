#!/usr/bin/env python3
import struct
import sys
from pathlib import Path
import numpy as np
from PIL import Image


class LzssDecompressor:
    __slots__ = ('data', 'size')
    
    def __init__(self, data: bytes):
        self.data = data
        self.size = len(data)
    
    def decompress(self, comp_size: int) -> bytes:
        data, limit = self.data, min(comp_size, self.size)
        window, pos, output = bytearray(0x1000), 0xfee, bytearray()
        i, flags = 0, 0
        
        while i < limit:
            flags >>= 1
            if not (flags & 0x100):
                if i >= limit: break
                flags = 0xff00 | data[i]
                i += 1
            
            if flags & 1:
                if i >= limit: break
                byte = data[i]
                i += 1
                output.append(byte)
                window[pos] = byte
                pos = (pos + 1) & 0xfff
            else:
                if i + 1 >= limit: break
                b1, b2 = data[i], data[i + 1]
                i += 2
                offset, length = b1 | ((b2 & 0xf0) << 4), (b2 & 0x0f) + 3
                for _ in range(length):
                    byte = window[offset & 0xfff]
                    output.append(byte)
                    window[pos] = byte
                    offset += 1
                    pos = (pos + 1) & 0xfff
        
        return bytes(output)


class PakExtractor:
    def __init__(self, pak_path: str):
        self.pak_path = pak_path
    
    def _xor_decrypt(self, data: bytes) -> bytes:
        arr = np.frombuffer(data, dtype=np.uint8).copy()
        arr ^= np.arange(len(arr), dtype=np.uint8)
        return bytes(arr)
    
    def _read_index(self, f) -> list:
        header = f.read(0x1c)
        index_size, file_count, data_offset = struct.unpack('<III', header[0x10:0x1c])
        compressed = f.read(index_size)
        index_data = LzssDecompressor(self._xor_decrypt(compressed)).decompress(index_size)
        
        files = []
        for i in range(file_count):
            entry = index_data[i * 0x28:(i + 1) * 0x28]
            name = entry[:0x20].split(b'\x00')[0].decode('shift-jis', errors='ignore')
            rel_offset, size = struct.unpack('<II', entry[0x20:0x28])
            files.append({'name': name, 'offset': data_offset + rel_offset, 'size': size})
        return files
    
    def _decode_image(self, data: bytes) -> Image.Image:
        header = struct.unpack('<10I', data[:40])
        comp_size, w, h, bpp = header[0], header[4], header[5], header[6]
        
        raw = data[40:]
        pixels = LzssDecompressor(raw).decompress(comp_size) if comp_size else raw
        
        if bpp == 8:
            pal = np.frombuffer(pixels[:1024], dtype=np.uint8).reshape(256, 4)
            idx = np.frombuffer(pixels[1024:1024 + w * h], dtype=np.uint8).reshape(h, w)
            bgra = pal[idx]
            if np.all(bgra[:, :, 3] == 0):
                return Image.fromarray(bgra[:, :, [2, 1, 0]], 'RGB')
            return Image.fromarray(bgra[:, :, [2, 1, 0, 3]], 'RGBA')
        elif bpp == 24:
            bgr = np.frombuffer(pixels[:w * h * 3], dtype=np.uint8).reshape(h, w, 3)
            return Image.fromarray(bgr[:, :, ::-1], 'RGB')
        elif bpp == 32:
            bgra = np.frombuffer(pixels[:w * h * 4], dtype=np.uint8).reshape(h, w, 4)
            if np.all(bgra[:, :, 3] == 0):
                return Image.fromarray(bgra[:, :, [2, 1, 0]], 'RGB')
            return Image.fromarray(bgra[:, :, [2, 1, 0, 3]], 'RGBA')
        
        raise ValueError(f"bpp={bpp}")
    
    def extract_all(self, output_dir: str):
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)
        
        with open(self.pak_path, 'rb') as f:
            files = self._read_index(f)
            ok, fail = 0, 0
            
            for i, info in enumerate(files, 1):
                print(f"[{i}/{len(files)}] {info['name']}", end=' ... ')
                try:
                    f.seek(info['offset'])
                    img = self._decode_image(f.read(info['size']))
                    out_file = output_path / f"{info['name']}.png"
                    out_file.parent.mkdir(parents=True, exist_ok=True)
                    img.save(out_file)
                    print(f"✓ {img.size[0]}x{img.size[1]} {img.mode}")
                    ok += 1
                except Exception as e:
                    print(f"✗ {e}")
                    fail += 1
            
            print(f"\n完成: {ok} 成功, {fail} 失败")


if __name__ == '__main__':
    if len(sys.argv) < 3:
        print("用法: python extract.py <PAK文件> <输出目录>")
        sys.exit(1)
    PakExtractor(sys.argv[1]).extract_all(sys.argv[2])