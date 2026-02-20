const API_BASE = import.meta.env.VITE_API_URL

/**
 * Encode a JSON file → CAT62 binary datablock.
 * Returns a Blob (application/octet-stream).
 * @param {File} file
 * @returns {Promise<Blob>}
 */
export async function encodeFile(file) {
  const form = new FormData()
  form.append('file', file)

  const res = await fetch(`${API_BASE}/encode`, {
    method: 'POST',
    body: form,
  })

  if (!res.ok) {
    let detail = `HTTP ${res.status}`
    try {
      const json = await res.json()
      detail = json.detail ?? detail
    } catch (_) {}
    throw new Error(detail)
  }

  return res.blob()
}

/**
 * Decode a CAT62 binary datablock → structured JSON.
 * Returns parsed JSON object { count, records }.
 * @param {File} file
 * @returns {Promise<{count: number, records: Array}>}
 */
export async function decodeFile(file) {
  const form = new FormData()
  form.append('file', file)

  const res = await fetch(`${API_BASE}/decode`, {
    method: 'POST',
    body: form,
  })

  if (!res.ok) {
    let detail = `HTTP ${res.status}`
    try {
      const json = await res.json()
      detail = json.detail ?? detail
    } catch (_) {}
    throw new Error(detail)
  }

  return res.json()
}
