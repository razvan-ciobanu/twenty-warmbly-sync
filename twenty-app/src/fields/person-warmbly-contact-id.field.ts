import { defineField, FieldType, STANDARD_OBJECT_UNIVERSAL_IDENTIFIERS } from 'twenty-sdk/define';

export default defineField({
  universalIdentifier: '0b42c960-cfcb-498c-918c-8868e6e6e98a',
  objectUniversalIdentifier: STANDARD_OBJECT_UNIVERSAL_IDENTIFIERS.person.universalIdentifier,
  name: 'warmblyContactId',
  type: FieldType.TEXT,
  label: 'Warmbly contact',
  description: 'Id of the linked Warmbly contact; written by crm-sync',
  icon: 'IconLink',
});
