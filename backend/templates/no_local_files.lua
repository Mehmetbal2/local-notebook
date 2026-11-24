-- Used by the DOCX export (services/export_service.py).
-- Markdown images are replaced by their alt text before pandoc's writer runs,
-- so ![](/any/path) in a chat answer or session title cannot make pandoc read a
-- local file and embed it in the document. Exports never embed images anyway.
function Image(el)
  return el.caption
end
