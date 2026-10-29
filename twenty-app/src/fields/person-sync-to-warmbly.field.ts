import { defineField, FieldType, STANDARD_OBJECT_UNIVERSAL_IDENTIFIERS } from 'twenty-sdk/define';

import { PERSON_SYNC_FIELD_ID } from 'src/constants/universal-identifiers';

export default defineField({
  universalIdentifier: PERSON_SYNC_FIELD_ID,
  objectUniversalIdentifier: STANDARD_OBJECT_UNIVERSAL_IDENTIFIERS.person.universalIdentifier,
  name: 'syncToWarmbly',
  type: FieldType.BOOLEAN,
  label: 'Sync to Warmbly',
  description: 'Sync this person to Warmbly (also on when its company is marked)',
  icon: 'IconSend',
  defaultValue: false,
});
