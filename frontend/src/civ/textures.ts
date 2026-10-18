import { RepeatWrapping, SRGBColorSpace, TextureLoader, type Texture } from "three";

/**
 * Photographic surfaces (Poly Haven, CC0), loaded once per repeat setting and
 * shared. Colour maps are sRGB; normal maps stay linear.
 */
const loader = new TextureLoader();
const cache = new Map<string, Texture>();

export function surface(name: string, repeat = 1, colour = true): Texture {
  const key = `${name}|${repeat}`;
  let texture = cache.get(key);
  if (!texture) {
    texture = loader.load(`/textures/${name}.jpg`);
    if (colour) texture.colorSpace = SRGBColorSpace;
    texture.wrapS = texture.wrapT = RepeatWrapping;
    texture.repeat.set(repeat, repeat);
    texture.anisotropy = 8;
    cache.set(key, texture);
  }
  return texture;
}
