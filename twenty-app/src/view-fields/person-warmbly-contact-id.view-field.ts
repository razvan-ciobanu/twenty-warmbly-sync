import { defineViewField } from 'twenty-sdk/define';

import { PERSON_WARMBLY_CONTACT_FIELD_ID } from 'src/constants/universal-identifiers';

// Person record page, "General" section (standard view and group ids).
export default defineViewField({
  universalIdentifier: 'f11177e1-ce35-4443-a7a9-07626898be37',
  viewUniversalIdentifier: '20202020-a002-4a02-8a02-ae0a1ea12001',
  viewFieldGroupUniversalIdentifier: '20202020-a002-4a02-8a02-ae0a1ea12101',
  fieldMetadataUniversalIdentifier: PERSON_WARMBLY_CONTACT_FIELD_ID,
  position: 2.2,
  isVisible: true,
});
