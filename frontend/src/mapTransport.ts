export interface MapPoint { x: number; y: number }

export interface MapSnapshot {
  frame_id: string
  width: number
  height: number
  resolution: number
  origin_x: number
  origin_y: number
  origin_yaw: number
  data: Int8Array
  path: MapPoint[]
  revision: number
  updated_at: string
}

export interface MapWireSnapshot {
  frame_id: string
  width: number
  height: number
  resolution: number
  origin_x: number
  origin_y: number
  origin_yaw: number
  data_encoding: 'zlib-base64-int8'
  data: string
  path: MapPoint[]
  revision: number
  updated_at: string
}

export const emptyMap: MapSnapshot = {
  frame_id: 'map', width: 0, height: 0, resolution: .05,
  origin_x: 0, origin_y: 0, origin_yaw: 0, data: new Int8Array(),
  path: [], revision: 0, updated_at: new Date().toISOString(),
}

function base64Bytes(value: string): Uint8Array {
  const binary = atob(value)
  const bytes = new Uint8Array(binary.length)
  for (let index = 0; index < binary.length; index += 1) bytes[index] = binary.charCodeAt(index)
  return bytes
}

async function inflate(compressed: Uint8Array): Promise<Uint8Array> {
  if (!compressed.length) return compressed
  if (typeof DecompressionStream === 'undefined') {
    throw new Error('当前浏览器不支持压缩地图传输，请使用最新版 Chrome。')
  }
  const stream = new Blob([compressed]).stream().pipeThrough(new DecompressionStream('deflate'))
  return new Uint8Array(await new Response(stream).arrayBuffer())
}

export async function decodeMapSnapshot(payload: MapWireSnapshot): Promise<MapSnapshot> {
  if (payload.data_encoding !== 'zlib-base64-int8') {
    throw new Error(`不支持的地图编码：${payload.data_encoding}`)
  }
  const raw = await inflate(base64Bytes(payload.data))
  if (raw.byteLength !== payload.width * payload.height) {
    throw new Error('地图数据长度与地图尺寸不一致')
  }
  return {
    ...payload,
    data: new Int8Array(raw.buffer, raw.byteOffset, raw.byteLength),
  }
}
