"""PDF save button — opens the OS "Save as" dialog.

``st.download_button`` only clicks an ``<a download>`` element. Whether that
shows a "Save as" dialog is decided by the browser and its download settings
(Chrome/Edge silently save to ``Downloads`` unless
"Ask where to save each file before downloading" is enabled), and a web page
cannot force that dialog.

To guarantee the native picker we use the File System Access API
(``window.showSaveFilePicker``) from a Custom Component v2. CCv2 renders in the
app's own document (no sandboxed iframe), so the call runs with the user's
click activation and the dialog always appears. Browsers without the API
(Firefox, Safari, non-secure origins) fall back to a regular download, and a
short hint tells the user how to make their browser ask for the location.
"""

from __future__ import annotations

import base64

import streamlit as st

_HTML = """
<div class="pdf-export">
  <button id="pdf-save" class="pdf-btn" type="button">
    <svg class="pdf-btn__icon" viewBox="0 0 24 24" aria-hidden="true" focusable="false">
      <path d="M12 3a1 1 0 0 1 1 1v9.59l3.3-3.3a1 1 0 1 1 1.4 1.42l-5 5a1 1 0 0 1-1.4 0l-5-5a1 1 0 1 1 1.4-1.42l3.3 3.3V4a1 1 0 0 1 1-1Z"/>
      <path d="M5 19a1 1 0 0 1 1-1h12a1 1 0 1 1 0 2H6a1 1 0 0 1-1-1Z"/>
    </svg>
    <span id="pdf-save-label">Descargar PDF</span>
  </button>
</div>
"""

_CSS = """
:host {
  display: block;
}

.pdf-export {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.pdf-btn {
  width: 100%;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  min-height: 2.5rem;
  padding: 0.5rem 1rem;
  border-radius: 9px;
  border: 1px solid var(--side-input-border, var(--st-widget-border-color, #cbd5e1));
  background: var(--side-input-bg, var(--st-secondary-background-color, #ffffff));
  color: var(--side-input-text, var(--st-text-color, #0f172a));
  font-family: var(--st-font, -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif);
  font-size: 0.875rem;
  font-weight: 500;
  line-height: 1.2;
  cursor: pointer;
  transition: border-color 120ms ease, color 120ms ease, opacity 120ms ease;
}

.pdf-btn:hover:not(:disabled) {
  border-color: var(--primary, var(--st-primary-color, #2563eb));
  color: var(--side-strong, var(--st-text-color, #0f172a));
}

.pdf-btn:focus-visible {
  outline: 2px solid var(--primary, var(--st-primary-color, #2563eb));
  outline-offset: 2px;
}

.pdf-btn:disabled {
  cursor: progress;
  opacity: 0.6;
}

.pdf-btn__icon {
  width: 18px;
  height: 18px;
  flex: none;
  fill: currentColor;
}
"""

_JS = """
export default function (component) {
  const { data, parentElement } = component;
  const button = parentElement.querySelector('#pdf-save');
  const label = parentElement.querySelector('#pdf-save-label');
  if (!button || !label) return;

  const payload = data || {};
  const fileName = payload.file_name || 'reporte.pdf';
  const pdfBase64 = payload.pdf_base64 || '';
  label.textContent = payload.label || 'Descargar PDF';

  const supportsPicker = typeof window.showSaveFilePicker === 'function';

  function toBytes(base64) {
    const binary = atob(base64);
    const bytes = new Uint8Array(binary.length);
    for (let i = 0; i < binary.length; i += 1) {
      bytes[i] = binary.charCodeAt(i);
    }
    return bytes;
  }

  function downloadWithAnchor(bytes) {
    const blob = new Blob([bytes], { type: 'application/pdf' });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement('a');
    anchor.href = url;
    anchor.download = fileName;
    anchor.style.display = 'none';
    document.body.appendChild(anchor);
    anchor.click();
    anchor.remove();
    setTimeout(() => URL.revokeObjectURL(url), 10000);
  }

  button.onclick = async () => {
    if (!pdfBase64 || button.disabled) return;

    let bytes;
    try {
      bytes = toBytes(pdfBase64);
    } catch (error) {
      return;
    }

    if (supportsPicker) {
      button.disabled = true;
      try {
        const handle = await window.showSaveFilePicker({
          suggestedName: fileName,
          types: [{ description: 'PDF', accept: { 'application/pdf': ['.pdf'] } }],
        });
        const writable = await handle.createWritable();
        await writable.write(new Blob([bytes], { type: 'application/pdf' }));
        await writable.close();
        return;
      } catch (error) {
        if (error && error.name === 'AbortError') return;
      } finally {
        button.disabled = false;
      }
    }

    downloadWithAnchor(bytes);
  };
}
"""

try:
    _PDF_SAVE_BUTTON = st.components.v2.component(
        "pdf_save_dialog_button",
        html=_HTML,
        css=_CSS,
        js=_JS,
    )
except (AttributeError, ImportError):  # Streamlit without Custom Components v2
    _PDF_SAVE_BUTTON = None

def pdf_save_button(
    pdf_bytes: bytes,
    file_name: str,
    *,
    label: str = "Descargar PDF",
    key: str = "pdf_save_button",
) -> None:
    """Render a button that saves the PDF through the native save dialog."""
    if _PDF_SAVE_BUTTON is None:
        st.download_button(
            label=label,
            data=pdf_bytes,
            file_name=file_name,
            mime="application/pdf",
            use_container_width=True,
            key=key,
        )
        return

    _PDF_SAVE_BUTTON(
        data={
            "pdf_base64": base64.b64encode(pdf_bytes).decode("ascii"),
            "file_name": file_name,
            "label": label,
        },
        key=key,
        width="stretch",
        height="content",
    )