import type { Map } from 'leaflet'

export function removeLeafletMap(map: Map | undefined) {
  if (!map) return
  // Leaflet 1.9 leaves its 250 ms zoom-completion timer running after remove().
  // Mark the animation finished before removing the panes so that timer exits
  // without accessing the detached map. Normal zoom animations stay enabled.
  const animatedMap = map as Map & { _animatingZoom?: boolean }
  animatedMap._animatingZoom = false
  map.remove()
}
