import { defineField, FieldType, STANDARD_OBJECT_UNIVERSAL_IDENTIFIERS } from 'twenty-sdk/define';

export default defineField({
  universalIdentifier: '62218c65-8f47-4086-b38d-852f7e9a1590',
  objectUniversalIdentifier: STANDARD_OBJECT_UNIVERSAL_IDENTIFIERS.person.universalIdentifier,
  name: 'syncToWarmbly',
  type: FieldType.BOOLEAN,
  label: 'Sync to Warmbly',
  description: 'Sync this person to Warmbly (also on when its company is marked)',
  icon: 'IconSend',
  defaultValue: false,
});
