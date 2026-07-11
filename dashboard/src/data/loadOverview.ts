import type {
  CubeArrayType,
  ObservedCube,
  OverviewBundle,
  OverviewLoader,
  OverviewMetadata,
} from '../types/overview'

const DEFAULT_METADATA_PATH = '/data/overview.json'

function assertMetadata(value: unknown): asserts value is OverviewMetadata {
  if (!value || typeof value !== 'object') {
    throw new Error('The Overview metadata response is not a JSON object.')
  }

  const candidate = value as Partial<OverviewMetadata>
  if (
    typeof candidate.schemaVersion !== 'string' ||
    candidate.application?.name !== 'NYC Crime Intelligence' ||
    !candidate.cube?.columns ||
    !candidate.dimensions?.weeks ||
    !candidate.dataRange?.latestCompleteWeek
  ) {
    throw new Error('The Overview metadata is incomplete or incompatible.')
  }
}

async function fetchOk(path: string): Promise<Response> {
  const response = await fetch(path, { cache: 'no-cache' })
  if (!response.ok) {
    throw new Error(`Dashboard data could not be loaded (${response.status}).`)
  }
  return response
}

async function decompressGzip(compressed: ArrayBuffer): Promise<ArrayBuffer> {
  if (typeof DecompressionStream === 'undefined') {
    throw new Error('This browser cannot unpack the aggregate dashboard data.')
  }

  const stream = new Blob([compressed])
    .stream()
    .pipeThrough(new DecompressionStream('gzip'))
  return new Response(stream).arrayBuffer()
}

function typedColumn(
  buffer: ArrayBuffer,
  type: CubeArrayType,
  offset: number,
  length: number,
): Uint8Array | Uint16Array | Uint32Array {
  switch (type) {
    case 'uint8':
      return new Uint8Array(buffer, offset, length)
    case 'uint16':
      return new Uint16Array(buffer, offset, length)
    case 'uint32':
      if (offset % Uint32Array.BYTES_PER_ELEMENT !== 0) {
        const view = new DataView(buffer, offset, length * Uint32Array.BYTES_PER_ELEMENT)
        const values = new Uint32Array(length)
        for (let index = 0; index < length; index += 1) {
          values[index] = view.getUint32(index * Uint32Array.BYTES_PER_ELEMENT, true)
        }
        return values
      }
      return new Uint32Array(buffer, offset, length)
  }
}

function decodeCube(metadata: OverviewMetadata, buffer: ArrayBuffer): ObservedCube {
  const { columns, rowCount } = metadata.cube
  const expected = ['counts', 'weeks', 'boroughs', 'precincts', 'offenses', 'laws']

  for (const name of expected) {
    const column = columns[name]
    if (!column || column.length !== rowCount) {
      throw new Error(`Aggregate cube column “${name}” is missing or incomplete.`)
    }
    if (column.offsetBytes + column.byteLength > buffer.byteLength) {
      throw new Error(`Aggregate cube column “${name}” exceeds the data file.`)
    }
  }

  if (new Uint16Array(new Uint8Array([1, 0]).buffer)[0] !== 1) {
    throw new Error('The aggregate cube requires a little-endian browser platform.')
  }

  const decoded: ObservedCube = {
    counts: typedColumn(
      buffer,
      columns.counts.type,
      columns.counts.offsetBytes,
      rowCount,
    ) as Uint32Array,
    weeks: typedColumn(
      buffer,
      columns.weeks.type,
      columns.weeks.offsetBytes,
      rowCount,
    ) as Uint16Array,
    boroughs: typedColumn(
      buffer,
      columns.boroughs.type,
      columns.boroughs.offsetBytes,
      rowCount,
    ) as Uint8Array,
    precincts: typedColumn(
      buffer,
      columns.precincts.type,
      columns.precincts.offsetBytes,
      rowCount,
    ) as Uint8Array,
    offenses: typedColumn(
      buffer,
      columns.offenses.type,
      columns.offenses.offsetBytes,
      rowCount,
    ) as Uint8Array,
    laws: typedColumn(
      buffer,
      columns.laws.type,
      columns.laws.offsetBytes,
      rowCount,
    ) as Uint8Array,
  }

  const weekOffsets = columns.weekRowOffsets
  if (weekOffsets) {
    const observedWeekCount =
      metadata.cube.observedWeekCount ?? weekOffsets.observedWeekCount
    if (
      observedWeekCount === undefined ||
      weekOffsets.type !== 'uint32' ||
      weekOffsets.length !== observedWeekCount + 1 ||
      weekOffsets.byteLength !== weekOffsets.length * Uint32Array.BYTES_PER_ELEMENT ||
      weekOffsets.offsetBytes + weekOffsets.byteLength > buffer.byteLength
    ) {
      throw new Error('Aggregate cube week offsets are invalid.')
    }
    const offsets = typedColumn(
      buffer,
      weekOffsets.type,
      weekOffsets.offsetBytes,
      weekOffsets.length,
    ) as Uint32Array
    if (offsets[0] !== 0 || offsets.at(-1) !== rowCount) {
      throw new Error('Aggregate cube week offsets do not span all rows.')
    }
    for (let index = 1; index < offsets.length; index += 1) {
      if (offsets[index] < offsets[index - 1]) {
        throw new Error('Aggregate cube week offsets are not ordered.')
      }
    }
    decoded.weekRowOffsets = offsets
  }

  return decoded
}

export const loadOverview: OverviewLoader = async (): Promise<OverviewBundle> => {
  const metadataResponse = await fetchOk(DEFAULT_METADATA_PATH)
  const unknownMetadata: unknown = await metadataResponse.json()
  assertMetadata(unknownMetadata)

  const metadata = unknownMetadata
  if (
    metadata.cube.encoding !== 'columnar-arrays-v1' ||
    metadata.cube.compression !== 'gzip' ||
    metadata.cube.byteOrder !== 'little-endian'
  ) {
    throw new Error('The aggregate cube encoding is not supported by this dashboard.')
  }

  const cubeResponse = await fetchOk(metadata.cube.path)
  const compressed = await cubeResponse.arrayBuffer()
  const bytes = new Uint8Array(compressed)
  const buffer =
    bytes[0] === 0x1f && bytes[1] === 0x8b
      ? await decompressGzip(compressed)
      : compressed
  const expectedBytes =
    metadata.cube.uncompressedByteLength ?? metadata.cube.uncompressedBytes
  if (expectedBytes !== undefined && buffer.byteLength !== expectedBytes) {
    throw new Error('The aggregate cube did not match its declared size.')
  }

  return { metadata, cube: decodeCube(metadata, buffer) }
}
