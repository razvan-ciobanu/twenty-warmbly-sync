import { defineViewField } from 'twenty-sdk/define';

import { COMPANY_DO_NOT_CONTACT_FIELD_ID } from 'src/constants/universal-identifiers';

// Company record page, "Contact" section (standard view and group ids).
export default defineViewField({
  universalIdentifier: '1cf279dd-cefe-4720-b924-cb496309d496',
  viewUniversalIdentifier: '20202020-a001-4a01-8a01-c0aba11c1001',
  viewFieldGroupUniversalIdentifier: '20202020-a001-4a01-8a01-c0aba11c1103',
  fieldMetadataUniversalIdentifier: COMPANY_DO_NOT_CONTACT_FIELD_ID,
  position: 4,
  isVisible: true,
});
