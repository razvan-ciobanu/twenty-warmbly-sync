import { defineField, FieldType, STANDARD_OBJECT_UNIVERSAL_IDENTIFIERS } from 'twenty-sdk/define';

import { PERSON_WARMBLY_CONTACT_FIELD_ID } from 'src/constants/universal-identifiers';

export default defineField({
  universalIdentifier: PERSON_WARMBLY_CONTACT_FIELD_ID,
  objectUniversalIdentifier: STANDARD_OBJECT_UNIVERSAL_IDENTIFIERS.person.universalIdentifier,
  name: 'warmblyContactId',
  type: FieldType.TEXT,
  label: 'Warmbly contact',
  description: 'Id of the linked Warmbly contact; written by crm-sync',
  icon: 'IconLink',
});
