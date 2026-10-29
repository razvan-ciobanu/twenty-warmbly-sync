import { defineViewField } from 'twenty-sdk/define';

import { COMPANY_SYNC_FIELD_ID } from 'src/constants/universal-identifiers';

// Company record page, "Contact" section (standard view and group ids).
export default defineViewField({
  universalIdentifier: '94f50294-5f59-4b8a-afc4-ab6f935b74ad',
  viewUniversalIdentifier: '20202020-a001-4a01-8a01-c0aba11c1001',
  viewFieldGroupUniversalIdentifier: '20202020-a001-4a01-8a01-c0aba11c1103',
  fieldMetadataUniversalIdentifier: COMPANY_SYNC_FIELD_ID,
  position: 3,
  isVisible: true,
});
