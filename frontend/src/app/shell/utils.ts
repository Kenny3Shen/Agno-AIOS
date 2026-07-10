export const NAV_GROUP_SIZES = [4, 3, 5, 2, 1] as const

export function splitNavigation<T>(items: T[]) {
  let offset = 0
  const groups = NAV_GROUP_SIZES.map((size) => {
    const group = items.slice(offset, offset + size)
    offset += size
    return group
  })
  if (offset < items.length) groups[groups.length - 1] = [...groups[groups.length - 1]!, ...items.slice(offset)]
  return groups
}

export function joinMenuGroups<T>(groups: T[][]) {
  const visible = groups.filter((group) => group.length > 0)
  return visible.flatMap((group, index) => index === 0 ? group : [{ type: 'divider' as const, key: `divider-${index}` }, ...group])
}
