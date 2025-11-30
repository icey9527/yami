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
    
    def decompress(self) -> bytes:
        window, pos, output = bytearray(0x1000), 0xfee, bytearray()
        i, flags = 0, 0
        
        while i < self.size:
            flags >>= 1
            if not (flags & 0x100):
                if i >= self.size: break
                flags = 0xff00 | self.data[i]
                i += 1
            
            if flags & 1:
                if i >= self.size: break
                byte = self.data[i]
                i += 1
                output.append(byte)
                window[pos] = byte
                pos = (pos + 1) & 0xfff
            else:
                if i + 1 >= self.size: break
                b1, b2 = self.data[i], self.data[i + 1]
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
    
    def _read_index(self, f) -> list:
        header = f.read(0x48)
        file_count = struct.unpack('<I', header[0x3c:0x40])[0]
        data_offset = struct.unpack('<I', header[0x40:0x44])[0]
        index_offset = struct.unpack('<I', header[0x44:0x48])[0]
        index_size = struct.unpack('<I', header[0x34:0x38])[0]
        
        f.seek(index_offset)
        index_data = LzssDecompressor(f.read(index_size)).decompress()
        
        files = []
        for i in range(file_count):
            entry = index_data[i * 0x68:(i + 1) * 0x68]
            name = entry[:0x40].split(b'\x00')[0].decode('cp936', errors='ignore')
            rel_offset, size = struct.unpack('<II', entry[0x40:0x48])
            files.append({'name': name, 'offset': data_offset + rel_offset, 'size': size})
        
        return files
    
    def _parse_image_block(self, data: bytes, offset: int) -> dict:
        header = struct.unpack('<29I', data[offset:offset + 0x74])
        return {
            'comp_size': header[1],
            'uncomp_size': header[2],
            'data_offset': header[3],
            'width': header[5],
            'height': header[6],
            'bpp': header[7]
        }
    
    def _decode_image(self, pixels: bytes, w: int, h: int, bpp: int) -> Image.Image:
        if bpp == 8:
            pal = np.frombuffer(pixels[:1024], dtype=np.uint8).reshape(256, 4)
            idx = np.frombuffer(pixels[1024:1024 + w * h], dtype=np.uint8).reshape(h, w)
            bgra = pal[idx]
            if np.all(bgra[:, :, 3] == 0):
                return Image.fromarray(bgra[:, :, [2, 1, 0]], 'RGB')
            return Image.fromarray(bgra[:, :, [2, 1, 0, 3]], 'RGBA')
        elif bpp == 0x18:
            bgr = np.frombuffer(pixels[:w * h * 3], dtype=np.uint8).reshape(h, w, 3)
            return Image.fromarray(bgr[:, :, ::-1], 'RGB')
        elif bpp == 0x20:
            bgra = np.frombuffer(pixels[:w * h * 4], dtype=np.uint8).reshape(h, w, 4)
            if np.all(bgra[:, :, 3] == 0):
                return Image.fromarray(bgra[:, :, [2, 1, 0]], 'RGB')
            return Image.fromarray(bgra[:, :, [2, 1, 0, 3]], 'RGBA')
        
        raise ValueError(f"bpp={bpp}")
    
    def _extract_images(self, data: bytes) -> list:
        images = []
        offset = 0
        idx = 0
        
        while offset + 0x74 <= len(data):
            block = self._parse_image_block(data, offset)
            data_start = offset + block['data_offset']
            
            if data_start + block['comp_size'] > len(data):
                break
            
            compressed = data[data_start:data_start + block['comp_size']]
            pixels = LzssDecompressor(compressed).decompress()
            
            try:
                img = self._decode_image(pixels, block['width'], block['height'], block['bpp'])
                images.append({'image': img, 'index': idx, 'size': f"{block['width']}x{block['height']}"})
                idx += 1
            except:
                pass
            
            offset = data_start + block['comp_size']
            offset = (offset + 3) & ~3
        
        return images
    
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
                    data = f.read(info['size'])
                    images = self._extract_images(data)
                    
                    if not images:
                        print("- 无图像")
                        continue
                    
                    if len(images) == 1:
                        out_file = output_path / f"{info['name']}.png"
                        images[0]['image'].save(out_file)
                        print(f"✓ {images[0]['size']}")
                    else:
                        sub_dir = output_path / info['name']
                        sub_dir.mkdir(exist_ok=True)
                        for img_data in images:
                            out_file = sub_dir / f"{img_data['index']:03d}_{img_data['size']}.png"
                            img_data['image'].save(out_file)
                        print(f"✓ {len(images)} 图像")
                    
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