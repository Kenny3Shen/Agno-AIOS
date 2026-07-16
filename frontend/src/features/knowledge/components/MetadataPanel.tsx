import { Drawer, Grid, Typography } from 'antd'
import { CopyableValue, MetadataDescriptions } from '@/shared/ui/MetadataDescriptions'
import { useFormatDate } from '@/shared/lib/format'
import type { Document } from '../types'
import { useTranslation } from 'react-i18next'

export function MetadataPanel({
  document,
  open,
  onClose,
}: {
  document: Document | null
  open: boolean
  onClose: () => void
}) {
  const { t } = useTranslation('knowledge')
  const formatDate = useFormatDate()
  const screens = Grid.useBreakpoint()
  const metadata = Object.fromEntries(
    Object.entries(document?.metadata ?? {}).filter(([key]) => !['title', 'source', 'owner_user_id', 'user_id', 'file_path'].includes(key))
  )

  return (
    <Drawer
      open={open}
      onClose={onClose}
      destroyOnHidden
      title={t('metadataTitle')}
      size={screens.lg ? 560 : 'calc(100vw - 32px)'}
    >
      {document ? (
        <MetadataDescriptions
          items={[
            { key: 'title', label: t('columns.title'), children: <Typography.Text strong>{document.title}</Typography.Text> },
            { key: 'id', label: t('metaId'), children: <CopyableValue value={document.id} /> },
            { key: 'source', label: t('columns.source'), children: document.source || '-' },
            { key: 'created', label: t('created'), children: formatDate(document.created_at) },
            { key: 'updated', label: t('updated'), children: formatDate(document.updated_at || document.created_at) },
            { key: 'owner', label: t('owner'), children: <CopyableValue value={document.owner_user_id} /> },
          ]}
          value={metadata}
        />
      ) : (
        <div className="empty-panel">{t('selectDocMeta')}</div>
      )}
    </Drawer>
  )
}
