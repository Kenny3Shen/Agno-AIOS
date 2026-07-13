import { Select, type SelectProps } from 'antd'
import { useTranslation } from 'react-i18next'
import type { ResourceVisibility } from '@/shared/types/common'

export function VisibilitySelect(props: Omit<SelectProps<ResourceVisibility>, 'options'>) {
  const { t } = useTranslation('common')
  const options: SelectProps<ResourceVisibility>['options'] = [
    { value: 'private', label: t('private') },
    { value: 'public', label: t('public') },
  ]
  return <Select<ResourceVisibility> {...props} options={options} />
}
