import { defineField, FieldType, STANDARD_OBJECT_UNIVERSAL_IDENTIFIERS } from 'twenty-sdk/define';

export default defineField({
  universalIdentifier: '6e85eb9e-f2be-4dc8-8411-4a8955512301',
  objectUniversalIdentifier: STANDARD_OBJECT_UNIVERSAL_IDENTIFIERS.company.universalIdentifier,
  name: 'syncToWarmbly',
  type: FieldType.BOOLEAN,
  label: 'Sync to Warmbly',
  description: 'Sync this company (its generic address and all its people) to Warmbly',
  icon: 'IconSend',
  defaultValue: false,
});
