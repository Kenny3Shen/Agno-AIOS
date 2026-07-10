import { Select, type SelectProps } from 'antd'
import type { ResourceVisibility } from '@/shared/types/common'

const options: SelectProps<ResourceVisibility>['options'] = [
  { value: 'private', label: 'Private' },
  { value: 'public', label: 'Public' },
]

export function VisibilitySelect(props: Omit<SelectProps<ResourceVisibility>, 'options'>) {
  return <Select<ResourceVisibility> {...props} options={options} />
}
