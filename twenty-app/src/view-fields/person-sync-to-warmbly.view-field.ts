import { defineViewField } from 'twenty-sdk/define';

import { PERSON_SYNC_FIELD_ID } from 'src/constants/universal-identifiers';

// Person record page, "General" section (standard view and group ids).
export default defineViewField({
  universalIdentifier: '1335302d-da50-44b1-aadd-4be34c0a8362',
  viewUniversalIdentifier: '20202020-a002-4a02-8a02-ae0a1ea12001',
  viewFieldGroupUniversalIdentifier: '20202020-a002-4a02-8a02-ae0a1ea12101',
  fieldMetadataUniversalIdentifier: PERSON_SYNC_FIELD_ID,
  position: 2,
  isVisible: true,
});
