import { describe, expect, it } from 'vitest'

import { formatKnowledgeMetadataBadges } from './knowledge-view.ts'

describe('knowledge view helpers', () => {
  it('limits long metadata values so document cards cannot overflow', () => {
    const badges = formatKnowledgeMetadataBadges({
      file_name:
        'INVERSE_HALFTONING_VIA_WEIGHTED_SOBEL_CONDITIONED_DIFFUSION_MODEL.md',
      source:
        'upload:MinerU_markdown_INVERSE_HALFTONING_VIA_WEIGHTED_SOBEL_CONDITIONED_DIFFUSION_MODEL',
    })

    expect(badges).toEqual([
      {
        key: 'file_name',
        value: 'INVERSE_HALFTONING_VIA_WEIGHTED_SOBEL_CONDITIONED_DIFFUSION...',
        title:
          'file_name: INVERSE_HALFTONING_VIA_WEIGHTED_SOBEL_CONDITIONED_DIFFUSION_MODEL.md',
      },
      {
        key: 'source',
        value: 'upload:MinerU_markdown_INVERSE_HALFTONING_VIA_WEIGHTED_SOBE...',
        title:
          'source: upload:MinerU_markdown_INVERSE_HALFTONING_VIA_WEIGHTED_SOBEL_CONDITIONED_DIFFUSION_MODEL',
      },
    ])
  })
})
