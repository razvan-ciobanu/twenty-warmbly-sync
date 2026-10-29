import { defineViewField } from 'twenty-sdk/define';

import { COMPANY_EMAILS_FIELD_ID } from 'src/constants/universal-identifiers';

// Company record page, "Contact" section (standard view and group ids).
export default defineViewField({
  universalIdentifier: '1b48b09f-907a-4226-a6ab-06cf02cfd933',
  viewUniversalIdentifier: '20202020-a001-4a01-8a01-c0aba11c1001',
  viewFieldGroupUniversalIdentifier: '20202020-a001-4a01-8a01-c0aba11c1103',
  fieldMetadataUniversalIdentifier: COMPANY_EMAILS_FIELD_ID,
  position: 2,
  isVisible: true,
});
