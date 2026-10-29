import { defineViewField } from 'twenty-sdk/define';

import { COMPANY_WARMBLY_CONTACT_FIELD_ID } from 'src/constants/universal-identifiers';

// Company record page, "Contact" section (standard view and group ids).
export default defineViewField({
  universalIdentifier: '95c41a57-0211-4304-a68e-281f5748aeea',
  viewUniversalIdentifier: '20202020-a001-4a01-8a01-c0aba11c1001',
  viewFieldGroupUniversalIdentifier: '20202020-a001-4a01-8a01-c0aba11c1103',
  fieldMetadataUniversalIdentifier: COMPANY_WARMBLY_CONTACT_FIELD_ID,
  position: 5,
  isVisible: true,
});
