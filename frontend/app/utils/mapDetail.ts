export function mapDetail(title: string, subtitle: string, rows: [string, string][], notes: string[] = []) {
  const root = document.createElement('div')
  root.className = 'map-detail'
  const heading = document.createElement('strong')
  heading.className = 'map-detail-title'
  heading.textContent = title
  root.appendChild(heading)
  if (subtitle) {
    const description = document.createElement('div')
    description.className = 'map-detail-subtitle'
    description.textContent = subtitle
    root.appendChild(description)
  }
  const list = document.createElement('dl')
  list.className = 'map-detail-rows'
  for (const [label, value] of rows) {
    const row = document.createElement('div')
    const term = document.createElement('dt')
    const data = document.createElement('dd')
    term.textContent = label
    data.textContent = value
    row.append(term, data)
    list.appendChild(row)
  }
  root.appendChild(list)
  if (notes.length) {
    const context = document.createElement('div')
    context.className = 'map-detail-notes'
    for (const note of notes) {
      const paragraph = document.createElement('p')
      paragraph.textContent = note
      context.appendChild(paragraph)
    }
    root.appendChild(context)
  }
  return root
}
