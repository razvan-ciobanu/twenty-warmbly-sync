import { defineViewField } from 'twenty-sdk/define';

import { PERSON_DO_NOT_CONTACT_FIELD_ID } from 'src/constants/universal-identifiers';

// Person record page, "General" section (standard view and group ids).
export default defineViewField({
  universalIdentifier: 'ef3190f8-70ae-418b-851b-53e71fca63ed',
  viewUniversalIdentifier: '20202020-a002-4a02-8a02-ae0a1ea12001',
  viewFieldGroupUniversalIdentifier: '20202020-a002-4a02-8a02-ae0a1ea12101',
  fieldMetadataUniversalIdentifier: PERSON_DO_NOT_CONTACT_FIELD_ID,
  position: 2.1,
  isVisible: true,
});
