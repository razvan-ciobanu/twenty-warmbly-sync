import { defineField, FieldType, STANDARD_OBJECT_UNIVERSAL_IDENTIFIERS } from 'twenty-sdk/define';

import { COMPANY_SYNC_FIELD_ID } from 'src/constants/universal-identifiers';

export default defineField({
  universalIdentifier: COMPANY_SYNC_FIELD_ID,
  objectUniversalIdentifier: STANDARD_OBJECT_UNIVERSAL_IDENTIFIERS.company.universalIdentifier,
  name: 'syncToWarmbly',
  type: FieldType.BOOLEAN,
  label: 'Sync to Warmbly',
  description: 'Sync this company (its generic address and all its people) to Warmbly',
  icon: 'IconSend',
  defaultValue: false,
});
